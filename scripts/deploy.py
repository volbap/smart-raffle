from brownie import Raffle, SmartRaffleCoin, accounts, config, network
from web3 import Web3


def get_owner_account():
    return accounts.add(config["wallets"]["owner_key"])


def get_beneficiary_account():
    return accounts.add(config["wallets"]["beneficiary_key"])


def get_participant_account():
    return accounts.add(config["wallets"]["participant_key"])


def main():
    # deploy_raffle()
    buy_tickets()


def buy_tickets():
    raffle = Raffle[-1]
    participant = get_participant_account()
    approve_token_if_necessary(raffle, Web3.toWei(100, "ether"), participant)
    raffle.buyTicket(8, {"from": participant})
    raffle.buyTicket(9, {"from": participant})


def deploy_raffle():
    # https://rinkeby.etherscan.io/address/0x724186654EAb957633F1b9B5dA9B3aeFa327687A
    # https://rinkeby.etherscan.io/address/0xc5Cd06629d47A9D544f7d00E1Cd47AD840e70374
    owner = get_owner_account()
    beneficiary = get_beneficiary_account()

    network_config = config["networks"][network.show_active()]
    token_address = network_config["token_address"]
    vrf_link_token = network_config["vrf_link_token"]
    vrf_coordinator = network_config["vrf_coordinator"]
    vrf_key_hash = network_config["vrf_key_hash"]
    vrf_link_fee = network_config["vrf_link_fee"]
    ticket_price = Web3.toWei(5, "ether")
    ticket_min_number = 1
    ticket_max_number = 200
    profit_factor = 20  # 20% goes to beneficiary, 80% goes to winner
    publish_source = network_config["publish_source"]

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
        {"from": owner},
        publish_source=publish_source,
    )

    print("🪂 Deployed Raffle contract")
    return raffle


def deploy_smart_raffle_coin():
    owner = get_owner_account()
    initial_supply = Web3.toWei(10_000_000, "ether")
    SmartRaffleCoin.deploy(initial_supply, {"from": owner})


def approve_token_if_necessary(raffle, amount, account):
    token = SmartRaffleCoin[-1]
    if token.allowance(account, raffle) < amount:
        token.approve(raffle, amount, {"from": account})


def approve_smart_raffle_coin(spender):
    owner = get_owner_account()
    approve_amount = Web3.toWei(1_000, "ether")
    SmartRaffleCoin[-1].approve(spender, approve_amount, {"from": owner})
