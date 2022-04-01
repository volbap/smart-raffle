from brownie import RaffleManager, config, network
from scripts.helpers import get_account

TICKET_PRICE = 10
TICKET_MIN_NUMBER = 1
TICKET_MAX_NUMBER = 100


def main():
    deploy_raffle_manager()


def deploy_raffle_manager():
    account = get_account()
    network_config = config["networks"][network.show_active()]
    usdc_token = network_config["usdc_token"]
    vrf_coordinator = network_config["vrf_coordinator"]
    vrf_link_fee = network_config["vrf_link_fee"]
    vrf_key_hash = network_config["vrf_key_hash"]
    link_token = network_config["link_token"]
    publish_source = network_config.get("publish_source", False)
    manager = RaffleManager.deploy(
        TICKET_PRICE,
        TICKET_MIN_NUMBER,
        TICKET_MAX_NUMBER,
        usdc_token,
        vrf_coordinator,
        vrf_link_fee,
        vrf_key_hash,
        link_token,
        {"from": account},
        publish_source=publish_source,
    )
    print("🪂 Deployed RaffleManager contract")
    return manager
