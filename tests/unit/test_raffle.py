from inspect import signature

from pyparsing import nullDebugAction
from brownie import (
    accounts,
    config,
    exceptions,
    interface,
    network,
    Contract,
    Raffle,
    MockERC20,
    MockVRFCoordinator,
    MockLinkToken,
)
import pytest

# TODO: Add ->  if network.show_active() not in LOCAL_BLOCKCHAIN_ENVIRONMENTS: pytest.skip()
# TODO: Test events
# TODO: syntax-sugar for 'with pytest.raises(exceptions.VirtualMachineError):'


def fund_with_link(manager, amount=10_0000000000_000000000):
    link_token_address = manager.vrfLinkToken()
    link_token = Contract.from_abi(
        MockLinkToken._name, link_token_address, MockLinkToken.abi
    )
    txn = link_token.transfer(manager, amount, get_owner_signature())
    print("💰 RaffleManager contract now has some LINK!")
    return txn


def approve_token(address, amount):
    raffle = Raffle[-1]
    token_address = raffle.tokenAddress()
    token = interface.IERC20(token_address)
    token.approve(raffle, amount, {"from": address})
    return token


def transfer_token(to_address, amount):
    raffle = Raffle[-1]
    token_address = raffle.tokenAddress()
    token = interface.IERC20(token_address)
    token.transfer(to_address, amount, get_owner_signature())
    return token


"""Returns the first account from the list.

This account is used to deploy contracts, meaning:
- It can call `onlyOwner` functions in `Raffle`.
- It owns the total supply of the `MockERC20` tokens.
"""


def get_owner_signature():
    return {"from": get_owner_account()}


def get_owner_account():
    return accounts[0]


def get_alternative_account():
    return accounts[8]


def get_beneficiary_account():
    return accounts[9]


def deploy_raffle():
    signature = get_owner_signature()
    beneficiary = get_beneficiary_account()

    network_config = config["networks"][network.show_active()]
    token_address = MockERC20.deploy(signature)
    vrf_link_token = MockLinkToken.deploy(signature)
    vrf_coordinator = MockVRFCoordinator.deploy(vrf_link_token, signature)
    vrf_key_hash = network_config["vrf_key_hash"]
    vrf_link_fee = network_config["vrf_link_fee"]
    ticket_price = 5
    ticket_min_number = 1
    ticket_max_number = 200
    profit_factor = 20  # 20% goes to beneficiary, 80% goes to winner

    raffle = Raffle.deploy(
        token_address,
        ticket_price,
        ticket_min_number,
        ticket_max_number,
        profit_factor,
        beneficiary,
        vrf_coordinator,
        vrf_key_hash,
        vrf_link_fee,
        vrf_link_token,
        signature,
    )

    assert raffle.tokenAddress() == token_address
    assert raffle.ticketPrice() == ticket_price
    assert raffle.ticketMinNumber() == ticket_min_number
    assert raffle.ticketMaxNumber() == ticket_max_number
    assert raffle.profitFactor() == profit_factor
    assert raffle.beneficiaryAddress() == beneficiary
    assert raffle.vrfKeyHash() == vrf_key_hash
    assert raffle.vrfLinkFee() == vrf_link_fee
    assert raffle.vrfLinkToken() == vrf_link_token

    return raffle


def test_open_tickets_sale_success():
    manager = deploy_raffle()
    assert manager.currentState() == 0  # RaffleState.closed

    manager.openTicketsSale(get_owner_signature())

    assert manager.currentState() == 1  # RaffleState.open


def test_open_tickets_sale_should_revert_for_non_owners():
    raffle = deploy_raffle()
    non_owner = get_alternative_account()
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.openTicketsSale({"from": non_owner})


def test_open_tickets_sale_should_revert_if_already_open():
    raffle = deploy_raffle()

    raffle.openTicketsSale(get_owner_signature())

    with pytest.raises(exceptions.VirtualMachineError):
        raffle.openTicketsSale(get_owner_signature())


def test_buy_ticket_success():
    raffle = deploy_raffle()
    owner = get_owner_account()
    signature = get_owner_signature()
    token = approve_token(owner, 10)
    initial_balance = token.balanceOf(owner)
    ticket_price = 5

    # Open a raffle and buy 2 tickets
    raffle.openTicketsSale(signature)
    raffle.buyTicket(2, signature)
    raffle.buyTicket(3, signature)

    # Assert some tickets that do not belong to the buyer
    assert raffle.ticketAddress(0) != owner
    assert raffle.ticketAddress(1) != owner

    # Assert tickets belonging to the buyer
    assert raffle.ticketAddress(2) == owner
    assert raffle.ticketAddress(3) == owner

    # Assert sold tickets
    assert raffle.soldTickets(0) == 2
    assert raffle.soldTickets(1) == 3

    # Assert buyer's token balance
    expected_balance = initial_balance - 2 * ticket_price
    assert token.balanceOf(owner) == expected_balance


def test_buy_ticket_should_revert_when_raffle_is_not_open():
    raffle = deploy_raffle()
    owner = get_owner_account()
    approve_token(owner, 10)

    with pytest.raises(exceptions.VirtualMachineError):
        raffle.buyTicket(7, get_owner_signature())


def test_buy_ticket_should_revert_when_buyer_has_not_enough_balance():
    raffle = deploy_raffle()
    owner = get_owner_account()
    poor_account = get_alternative_account()  # without tokens
    approve_token(owner, 5)
    approve_token(poor_account, 5)

    raffle.openTicketsSale(get_owner_signature())

    with pytest.raises(exceptions.VirtualMachineError):
        raffle.buyTicket(7, {"from": poor_account})


def test_buy_ticket_should_revert_for_invalid_ticket_number():
    raffle = deploy_raffle()
    owner = get_owner_account()
    approve_token(owner, 5)

    raffle.openTicketsSale(get_owner_signature())

    with pytest.raises(exceptions.VirtualMachineError):
        raffle.buyTicket(201, get_owner_signature())


def test_buy_ticket_should_revert_for_already_sold_ticket():
    raffle = deploy_raffle()
    owner = get_owner_account()
    approve_token(owner, 10)

    raffle.openTicketsSale(get_owner_signature())
    raffle.buyTicket(66, get_owner_signature())

    with pytest.raises(exceptions.VirtualMachineError):
        raffle.buyTicket(66, get_owner_signature())


def test_get_accumulated_amounts():
    raffle = deploy_raffle()
    owner = get_owner_account()
    signature = get_owner_signature()
    approve_token(owner, 15)

    raffle.openTicketsSale(signature)
    assert raffle.getTotalAccumulatedAmount() == 0
    assert raffle.getCurrentPrizeAmount() == 0
    assert raffle.getCurrentProfitsAmount() == 0

    raffle.buyTicket(1, signature)
    assert raffle.getTotalAccumulatedAmount() == 5
    assert raffle.getCurrentPrizeAmount() == 4
    assert raffle.getCurrentProfitsAmount() == 1

    raffle.buyTicket(2, signature)
    assert raffle.getTotalAccumulatedAmount() == 10
    assert raffle.getCurrentPrizeAmount() == 8
    assert raffle.getCurrentProfitsAmount() == 2

    raffle.buyTicket(3, signature)
    assert raffle.getTotalAccumulatedAmount() == 15
    assert raffle.getCurrentPrizeAmount() == 12
    assert raffle.getCurrentProfitsAmount() == 3


def test_close_tickets_sale_should_revert_for_non_owners():
    raffle = deploy_raffle()
    non_owner = get_alternative_account()
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.closeTicketsSale({"from": non_owner})


def test_close_tickets_sale_should_revert_when_no_open_raffle():
    raffle = deploy_raffle()

    with pytest.raises(exceptions.VirtualMachineError):
        raffle.closeTicketsSale(get_owner_signature())


def test_close_tickets_sale_success():
    raffle = deploy_raffle()
    owner = get_owner_account()
    approve_token(owner, 5)

    raffle.openTicketsSale(get_owner_signature())
    raffle.buyTicket(1, get_owner_signature())
    raffle.closeTicketsSale(get_owner_signature())

    assert raffle.currentState() == 2  # RaffleState.salesFinished


def test_cancel_raffle_successfully_should_allow_users_to_claim_refunds():
    raffle = deploy_raffle()
    token = interface.IERC20(raffle.tokenAddress())
    raffle.openTicketsSale(get_owner_signature())

    (player_1, player_2, player_3) = (accounts[1], accounts[2], accounts[3])
    transfer_token(player_1, 100)
    transfer_token(player_2, 100)
    transfer_token(player_3, 100)
    approve_token(player_1, 5)
    approve_token(player_2, 5)
    approve_token(player_3, 10)

    raffle.buyTicket(7, {"from": player_1})
    raffle.buyTicket(51, {"from": player_2})
    raffle.buyTicket(88, {"from": player_3})
    raffle.buyTicket(42, {"from": player_3})

    # assert players balances after buying tickets
    assert token.balanceOf(player_1) == 95  # 100 - 5
    assert token.balanceOf(player_2) == 95  # 100 - 5
    assert token.balanceOf(player_3) == 90  # 100 - 10

    # users can't claim refunds if raffle is not cancelled
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimRefunds({"from": player_1})
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimRefunds({"from": player_2})
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimRefunds({"from": player_3})

    # let's cancel the raffle!
    raffle.cancelRaffle(get_owner_signature())

    # users can't buy tickets after raffle is cancelled
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.buyTicket(10, {"from": player_1})

    # users can claim refunds at this point
    raffle.claimRefunds({"from": player_1})
    raffle.claimRefunds({"from": player_2})
    raffle.claimRefunds({"from": player_3})

    # let's ensure users have been refunded
    assert token.balanceOf(player_1) == 100
    assert token.balanceOf(player_2) == 100
    assert token.balanceOf(player_3) == 100

    # users can't claim refunds more than once
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimRefunds({"from": player_1})
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimRefunds({"from": player_2})
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimRefunds({"from": player_3})


def test_cancel_raffle_should_revert_for_non_owners():
    raffle = deploy_raffle()
    non_owner = get_alternative_account()

    with pytest.raises(exceptions.VirtualMachineError):
        raffle.cancelRaffle({"from": non_owner})


def test_full_raffle_circuit():
    raffle = deploy_raffle()
    owner = get_owner_account()
    beneficiary = get_beneficiary_account()
    token = interface.IERC20(raffle.tokenAddress())

    (player_1, player_2, player_3) = (accounts[1], accounts[2], accounts[3])
    transfer_token(player_1, 100)
    transfer_token(player_2, 100)
    transfer_token(player_3, 100)
    approve_token(player_1, 5)
    approve_token(player_2, 5)
    approve_token(player_3, 10)

    # let's open the ticket sale
    raffle.openTicketsSale(get_owner_signature())

    # let's have players buying tickets
    raffle.buyTicket(7, {"from": player_1})
    raffle.buyTicket(51, {"from": player_2})
    raffle.buyTicket(88, {"from": player_3})
    raffle.buyTicket(42, {"from": player_3})

    # assert players balances after buying tickets
    assert token.balanceOf(player_1) == 95  # 100 - 5
    assert token.balanceOf(player_2) == 95  # 100 - 5
    assert token.balanceOf(player_3) == 90  # 100 - 10

    # what do we expect?
    expected_prize = 16
    expected_profits = 4
    expected_winner = player_3

    # no one can claim prizes / profits before the raffle is finished
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.redeemPrize({"from": expected_winner})
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimProfits({"from": beneficiary})

    # let's pick a winner...
    close_tickets_sale_and_simulate_winner_ticket_index(2)

    # assert winner-related variables
    assert raffle.obtainedRandomNumber() == 2
    assert raffle.winnerTicketNumber() == 88
    assert raffle.winnerAddress() == expected_winner

    # redeemPrize should revert when called by losers
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.redeemPrize({"from": player_1})
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.redeemPrize({"from": player_2})

    # redeemPrize should transfer prize amount to winner
    raffle.redeemPrize({"from": expected_winner})
    assert token.balanceOf(expected_winner) == 90 + expected_prize

    # winner should not be able to redeem the prize more than once
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.redeemPrize({"from": expected_winner})

    # claimProfits should only work for the beneficiary account
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimProfits({"from": owner})
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimProfits({"from": player_1})
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimProfits({"from": player_2})
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimProfits({"from": player_3})

    # claimProfits should transfer profits to beneficiary
    raffle.claimProfits({"from": beneficiary})
    assert token.balanceOf(beneficiary) == expected_profits

    # beneficiary should not be able to claim profits again
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.claimProfits({"from": beneficiary})

    # raffle cannot be cancelled at this point
    with pytest.raises(exceptions.VirtualMachineError):
        raffle.cancelRaffle(get_owner_signature())


def close_tickets_sale_and_simulate_winner_ticket_index(winner_ticket_index):
    raffle = Raffle[-1]
    fund_with_link(raffle)
    close_txn = raffle.closeTicketsSaleAndPickWinner(get_owner_signature())

    # We need to dig in the `RequestedRandomness event to get the `requestId`
    request_id = close_txn.events["RequestedRandomness"]["requestId"]

    # In order to trigger the `fulfillRandomness` function, we need to pretend
    # that we are the Chainlink VRF node and call the function that
    # triggers `fulfillRandomness`.
    # That function is `callBackWithRandomness, which triggers `rawFulfillRandomness.selector`,
    # which triggers `fulfillRandomness`.
    MockVRFCoordinator[-1].callBackWithRandomness(
        request_id, winner_ticket_index, raffle, get_owner_signature()
    )
