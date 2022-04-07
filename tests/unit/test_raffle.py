from inspect import signature

from pyparsing import nullDebugAction
from brownie import (
    accounts,
    config,
    exceptions,
    interface,
    network,
    RaffleManager,
    MockERC20,
    MockVRFCoordinator,
    MockLinkToken,
)
import pytest

from scripts.helpers import fund_with_link

# TODO: Add ->  if network.show_active() not in LOCAL_BLOCKCHAIN_ENVIRONMENTS: pytest.skip()


def approve_token(address, amount):
    manager = RaffleManager[-1]
    token_address = manager.tokenAddress()
    token = interface.IERC20(token_address)
    token.approve(manager, amount, {"from": address})
    return token


def transfer_token(to_address, amount):
    manager = RaffleManager[-1]
    account = get_main_account()
    token_address = manager.tokenAddress()
    token = interface.IERC20(token_address)
    token.transfer(to_address, amount, {"from": account})
    return token


"""Returns the first account from the list.

This account is used to deploy contracts, meaning:
- It can call `onlyOwner` functions in `RaffleManager`.
- It owns the total supply of the `MockERC20` tokens.
"""


def get_main_account():
    return accounts[0]


def get_alternative_account():
    return accounts[1]


def deploy_raffle_manager():
    account = get_main_account()
    signature = {"from": account}

    token_address = MockERC20.deploy(signature)
    token_decimals = 18

    vrf_link_token = MockLinkToken.deploy(signature)
    vrf_coordinator = MockVRFCoordinator.deploy(vrf_link_token, signature)

    network_config = config["networks"][network.show_active()]

    return RaffleManager.deploy(
        token_address,
        token_decimals,
        vrf_coordinator,
        network_config["vrf_key_hash"],
        network_config["vrf_link_fee"],
        vrf_link_token,
        signature,
    )


def test_open_raffle_success():
    manager = deploy_raffle_manager()
    account = get_main_account()
    ticket_price = 5
    ticket_min_number = 1
    ticket_max_number = 100

    assert manager.currentState() == 0  # RaffleState.closed

    manager.openRaffle(
        ticket_price, ticket_min_number, ticket_max_number, {"from": account}
    )

    assert manager.ticketPrice() == ticket_price
    assert manager.ticketMinNumber() == ticket_min_number
    assert manager.ticketMaxNumber() == ticket_max_number
    assert manager.currentState() == 1  # RaffleState.open


def test_open_raffle_should_revert_for_non_owners():
    manager = deploy_raffle_manager()
    non_owner = get_alternative_account()
    with pytest.raises(exceptions.VirtualMachineError):
        manager.openRaffle(5, 1, 100, {"from": non_owner})


def test_open_raffle_should_revert_when_ongoing_raffle():
    manager = deploy_raffle_manager()
    account = get_main_account()

    manager.openRaffle(5, 1, 100, {"from": account})

    with pytest.raises(exceptions.VirtualMachineError):
        manager.openRaffle(5, 1, 100, {"from": account})


def test_open_raffle_should_revert_for_invalid_ticket_numbers():
    manager = deploy_raffle_manager()
    account = get_main_account()
    with pytest.raises(exceptions.VirtualMachineError):
        manager.openRaffle(5, 100, 1, {"from": account})


def test_buy_ticket_success():
    manager = deploy_raffle_manager()
    account = get_main_account()
    token = approve_token(account, 10)
    initial_balance = token.balanceOf(account)
    ticket_price = 5

    # Open a raffle and buy 2 tickets
    manager.openRaffle(ticket_price, 1, 100, {"from": account})
    manager.buyTicket(2, {"from": account})
    manager.buyTicket(3, {"from": account})

    # Assert some tickets not owned by the buyer
    assert manager.ticketAddresses(0) != account
    assert manager.ticketAddresses(1) != account

    # Assert tickets owned by the buyer
    assert manager.ticketAddresses(2) == account
    assert manager.ticketAddresses(3) == account

    # Assert sold tickets
    assert manager.soldTickets(0) == 2
    assert manager.soldTickets(1) == 3

    # Assert buyer's token balance
    expected_balance = initial_balance - 2 * ticket_price
    assert token.balanceOf(account) == expected_balance


def test_buy_ticket_should_revert_when_raffle_is_not_open():
    manager = deploy_raffle_manager()
    account = get_main_account()
    approve_token(account, 10)

    with pytest.raises(exceptions.VirtualMachineError):
        manager.buyTicket(7, {"from": account})


def test_buy_ticket_should_revert_when_buyer_has_not_enough_balance():
    manager = deploy_raffle_manager()
    main_account = get_main_account()
    poor_account = get_alternative_account()  # without tokens
    approve_token(main_account, 5)
    approve_token(poor_account, 5)

    manager.openRaffle(5, 1, 100, {"from": main_account})

    with pytest.raises(exceptions.VirtualMachineError):
        manager.buyTicket(7, {"from": poor_account})


def test_buy_ticket_should_revert_for_invalid_ticket_number():
    manager = deploy_raffle_manager()
    account = get_main_account()
    approve_token(account, 5)

    manager.openRaffle(5, 1, 100, {"from": account})

    with pytest.raises(exceptions.VirtualMachineError):
        manager.buyTicket(101, {"from": account})


def test_buy_ticket_should_revert_for_already_sold_ticket():
    manager = deploy_raffle_manager()
    account = get_main_account()
    approve_token(account, 10)

    manager.openRaffle(5, 1, 100, {"from": account})
    manager.buyTicket(66, {"from": account})

    with pytest.raises(exceptions.VirtualMachineError):
        manager.buyTicket(66, {"from": account})


def test_get_current_prize_amount():
    manager = deploy_raffle_manager()
    account = get_main_account()
    approve_token(account, 15)

    manager.openRaffle(5, 1, 100, {"from": account})
    assert manager.getCurrentPrizeAmount() == 0

    manager.buyTicket(1, {"from": account})
    assert manager.getCurrentPrizeAmount() == 5

    manager.buyTicket(2, {"from": account})
    assert manager.getCurrentPrizeAmount() == 10

    manager.buyTicket(3, {"from": account})
    assert manager.getCurrentPrizeAmount() == 15


def test_close_raffle_should_revert_for_non_owners():
    manager = deploy_raffle_manager()
    non_owner = get_alternative_account()
    with pytest.raises(exceptions.VirtualMachineError):
        manager.closeRaffle({"from": non_owner})


def test_close_raffle_should_revert_when_no_open_raffle():
    manager = deploy_raffle_manager()
    account = get_main_account()

    with pytest.raises(exceptions.VirtualMachineError):
        manager.closeRaffle({"from": account})


def test_close_raffle_calculates_winner_and_prize_can_be_redeemed():
    manager = deploy_raffle_manager()
    account = get_main_account()
    token = interface.IERC20(manager.tokenAddress())
    (player_1, player_2, player_3) = (accounts[1], accounts[2], accounts[3])
    transfer_token(player_1, 100)
    transfer_token(player_2, 100)
    transfer_token(player_3, 100)
    approve_token(player_1, 5)
    approve_token(player_2, 5)
    approve_token(player_3, 10)

    manager.openRaffle(5, 1, 100, {"from": account})

    manager.buyTicket(7, {"from": player_1})
    manager.buyTicket(51, {"from": player_2})
    manager.buyTicket(88, {"from": player_3})
    manager.buyTicket(42, {"from": player_3})

    # assert players balances after buying tickets
    assert token.balanceOf(player_1) == 95  # 100 - 5
    assert token.balanceOf(player_2) == 95  # 100 - 5
    assert token.balanceOf(player_3) == 90  # 100 - 10

    # assert raffle prize amount
    assert manager.getCurrentPrizeAmount() == 20

    close_raffle_simulating_winner_ticket_index(2)

    # assert winner-related variables
    assert manager.lastRandomNumber() == 2
    assert manager.lastWinnerTicket() == 88
    assert manager.lastWinnerAddress() == player_3

    # assert how much each player can claim
    assert manager.addressToPrizeAmount(player_1) == 0
    assert manager.addressToPrizeAmount(player_2) == 0
    assert manager.addressToPrizeAmount(player_3) == 20

    # redeemPrize should revert when claimed by losers
    with pytest.raises(exceptions.VirtualMachineError):
        manager.redeemPrize({"from": player_1})
    with pytest.raises(exceptions.VirtualMachineError):
        manager.redeemPrize({"from": player_2})

    # redeemPrize should transfer prize amount to winner
    manager.redeemPrize({"from": player_3})
    assert token.balanceOf(player_3) == 110  # 90 + 20

    # redeemPrize should revert if prize has already been redeemed
    with pytest.raises(exceptions.VirtualMachineError):
        manager.redeemPrize({"from": player_3})

    # assert state has been properly reset
    assert manager.currentState() == 0  # RaffleState.closed
    assert manager.rafflesCount() == 1
    assert manager.ticketAddresses(7) != player_1
    assert manager.ticketAddresses(51) != player_2
    assert manager.ticketAddresses(88) != player_3
    assert manager.ticketAddresses(42) != player_3
    with pytest.raises(exceptions.VirtualMachineError):
        manager.soldTickets(0)


def close_raffle_simulating_winner_ticket_index(winner_ticket_index):
    account = get_main_account()
    manager = RaffleManager[-1]
    fund_with_link(manager)
    close_txn = manager.closeRaffle({"from": account})

    # We need to dig in the `RequestedRandomness event to get the `requestId`
    request_id = close_txn.events["RequestedRandomness"]["requestId"]

    # In order to trigger the `fulfillRandomness` function, we need to pretend
    # that we are the Chainlink VRF node and call the function that
    # triggers `fulfillRandomness`.
    # That function is `callBackWithRandomness, which triggers `rawFulfillRandomness.selector`,
    # which triggers `fulfillRandomness`.
    MockVRFCoordinator[-1].callBackWithRandomness(
        request_id, winner_ticket_index, manager, {"from": account}
    )
