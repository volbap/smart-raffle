from brownie import accounts, network, config, SmartRaffleCoin

FORKED_LOCAL_ENVIRONMENTS = ["mainnet-fork", "mainnet-fork-dev"]
LOCAL_BLOCKCHAIN_ENVIRONMENTS = ["development", "ganache-local"]

# Gets an account by index, from the accounts list.
# Typically used in local Ganache environments.
def get_account(index):
    return accounts[index]


# Gets an account by identifier
def get_account(id):
    return accounts.load(id)


# Gets the account based on the environment.
# - For a local environment, like Ganache, it will
# return the first account from the list of pre-defined
# accounts.
# - For a testnet environment, e.g. Rinkeby, it will
# spin up an account from the private key provided in the
# configuration file / environment variables.
def get_account():
    if (
        network.show_active() in LOCAL_BLOCKCHAIN_ENVIRONMENTS
        or network.show_active() in FORKED_LOCAL_ENVIRONMENTS
    ):
        return accounts[0]
    return accounts.add(config["wallets"]["from_key"])


def deploy_smart_raffle_coin():
    SmartRaffleCoin.deploy(TEN_MILLION_TOKENS, {"from": account})


def approve_smart_raffle_coin(spender):
    account = get_account()
    SmartRaffleCoin[-1].approve(
        spender, 10000000_0000000000_00000000, {"from": account}
    )


def fund_with_link(contract_address, amount=10_0000000000_000000000):
    account = get_account()
    link_token = config["networks"][network.show_active()]["link_token"]
    txn = link_token.transfer(contract_address, amount, {"from": account})
    txn.wait(1)
    print("💰 Fund RaffleManager contract with some LINK!")
    return txn
