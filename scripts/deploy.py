from brownie import RaffleManager, config, network
from scripts.helpers import get_account, fund_with_link, approve_smart_raffle_coin

TICKET_PRICE = 10_0000000000_00000000
TICKET_MIN_NUMBER = 1
TICKET_MAX_NUMBER = 200
TEN_MILLION_TOKENS = 10000000_0000000000_00000000

account = get_account()


def main():
    manager = deploy_raffle_manager()

    # deploy_smart_raffle_coin()

    # manager.openRaffle(
    #     TICKET_PRICE, TICKET_MIN_NUMBER, TICKET_MAX_NUMBER, {"from": account}
    # )
    # print("📭 Opened raffle")

    # approve_smart_raffle_coin(manager)

    # manager.buyTicket(17, {"from": account})
    # print("🎫 Bought ticket")

    # fund_with_link(manager)
    manager.closeRaffle({"from": account})


def deploy_raffle_manager():
    network_config = config["networks"][network.show_active()]
    token_address = network_config["token_address"]
    token_decimals = network_config["token_decimals"]
    vrf_coordinator = network_config["vrf_coordinator"]
    vrf_link_fee = network_config["vrf_link_fee"]
    vrf_key_hash = network_config["vrf_key_hash"]
    vrf_link_token = network_config["vrf_link_token"]
    publish_source = network_config.get("publish_source", False)
    manager = RaffleManager.deploy(
        token_address,
        token_decimals,
        vrf_coordinator,
        vrf_key_hash,
        vrf_link_fee,
        vrf_link_token,
        {"from": account},
        publish_source=publish_source,
    )
    print("🪂 Deployed RaffleManager contract")
    return manager


# https://rinkeby.etherscan.io/address/0xa8a4b76cf1b286c5188246d30fb330c291048301
