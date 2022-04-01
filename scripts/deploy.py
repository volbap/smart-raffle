from brownie import RaffleManager, config, network
from scripts.helpers import get_account


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
