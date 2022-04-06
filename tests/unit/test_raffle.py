from inspect import signature
from brownie import (
    accounts,
    config,
    exceptions,
    network,
    RaffleManager,
    MockERC20,
    MockVRFCoordinator,
    MockLinkToken,
)
import pytest


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
    account = get_alternative_account()
    with pytest.raises(exceptions.VirtualMachineError):
        manager.openRaffle(5, 1, 100, {"from": account})


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

    manager.openRaffle(5, 1, 100, {"from": account})
    manager.buyTicket(2, {"from": account})
    manager.buyTicket(3, {"from": account})

    assert manager.ticketAddresses(0) != account
    assert manager.ticketAddresses(1) != account
    assert manager.ticketAddresses(2) == account
    assert manager.ticketAddresses(3) == account
    assert manager().soldTickets(0) == 2
    assert manager().soldTickets(1) == 3
    # TODO: also assert ERC20 token spent


def test_buy_ticket_should_revert_when_raffle_is_not_open():
    manager = deploy_raffle_manager()
    account = get_main_account()

    with pytest.raises(exceptions.VirtualMachineError):
        manager.buyTicket(7, {"from": account})


def test_buy_ticket_should_revert_when_buyer_has_not_enough_balance():
    manager = deploy_raffle_manager()
    account = get_main_account()
    poor_account = get_alternative_account()  # without SRC tokens

    manager.openRaffle(5, 1, 100, {"from": account})

    with pytest.raises(exceptions.VirtualMachineError):
        manager.buyTicket(7, {"from": poor_account})


def test_buy_ticket_should_revert_for_invalid_ticket_number():
    manager = deploy_raffle_manager()
    account = get_main_account()

    manager.openRaffle(5, 1, 100, {"from": account})

    with pytest.raises(exceptions.VirtualMachineError):
        manager.buyTicket(101, {"from": account})


def test_buy_ticket_should_revert_for_already_sold_ticket():
    manager = deploy_raffle_manager()
    account = get_main_account()

    manager.openRaffle(5, 1, 100, {"from": account})
    manager.buyTicket(66, {"from": account})

    with pytest.raises(exceptions.VirtualMachineError):
        manager.buyTicket(66, {"from": account})


### TODO:
### Txns are reverting due to "ERC20: insuficient allowance"
### - call approve on the ERC20 so RaffleManager can spend the token on behalf of the accounts
