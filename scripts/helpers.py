from brownie import accounts, network, config, Contract

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
