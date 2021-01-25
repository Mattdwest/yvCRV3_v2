# TODO: Add tests here that show the normal operation of this strategy
#       Suggestions to include:
#           - strategy loading and unloading (via Vault addStrategy/revokeStrategy)
#           - change in loading (from low to high and high to low)
#           - strategy operation at different loading levels (anticipated and "extreme")

import pytest

from brownie import Wei, accounts, Contract, config
from brownie import Strategy3Poolv2

@pytest.mark.require_network("mainnet-fork")
def test_operation(pm, chain):
        dai_liquidity = accounts.at(
            "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7", force=True
        )  # using curve pool (lots of dai)

        crv3_liquidity = accounts.at(
            "0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490", force=True
        )  # yearn treasury (lots of crv3)

        crv_liquidity = accounts.at(
            "0xD533a949740bb3306d119CC777fa900bA034cd52", force=True
        )  # using curve vesting (lots of crv)

        weth_liquidity = accounts.at(
            "0x2F0b23f53734252Bda2277357e97e1517d6B042A", force=True
        )  # using MKR (lots of weth)

        rewards = accounts[2]
        gov = accounts[3]
        guardian = accounts[4]
        bob = accounts[5]
        alice = accounts[6]
        strategist = accounts[7]
        tinytim = accounts[8]
        proxy = accounts[9]

        # dai approval
        dai = Contract("0x6b175474e89094c44da98b954eedeac495271d0f", owner=gov)  # DAI token

        dai.approve(dai_liquidity, Wei("1000000 ether"), {"from": dai_liquidity})
        dai.transferFrom(dai_liquidity, gov, Wei("300000 ether"), {"from": dai_liquidity})


        threePool = Contract(
            "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7", owner=gov
        )  # crv3 pool address (threePool)
        #yCRV3 = Contract(
        #    "0x9cA85572E6A3EbF24dEDd195623F188735A5179f", owner=gov
        #)  # crv3 vault (threePool)
        unirouter = Contract.from_explorer(
            "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D", owner=gov
        )  # UNI router v2
        proxy = Contract.from_explorer(
            "0xc17adf949f524213a540609c386035d7d685b16f", owner = gov
        )       # StrategyProxy

        gauge = Contract.from_explorer(
            "0xbFcF63294aD7105dEa65aA58F8AE5BE2D9d0952A", owner = gov
        )       # threePool gauge

        govProxy = Contract.from_explorer(
                "0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", owner=gov
        )  # threePool gauge

        dai.approve(threePool, Wei("1000000 ether"), {"from": gov})


        #crv3 approval
        crv3 = Contract(
            "0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490", owner=gov
        )  # crv3 token address (threePool token)

        #depositing DAI to generate crv3 tokens.
        crv3.approve(crv3_liquidity, Wei("1000000 ether"), {"from": crv3_liquidity})
        threePool.add_liquidity([Wei("200000 ether"), 0, 0], 0, {"from": gov})

        #crv approval
        crv = Contract(
            "0xD533a949740bb3306d119CC777fa900bA034cd52", owner=gov
        )  # crv token address (DAO token)

        crv.approve(crv_liquidity, Wei("1000000 ether"), {"from": crv_liquidity})
        crv.transferFrom(crv_liquidity, gov, Wei("10000 ether"), {"from": crv_liquidity})

        #weth approval
        weth = Contract(
            "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", owner=gov
        )  # weth token address

        weth.approve(weth_liquidity, Wei("1000000 ether"), {"from": weth_liquidity})
        weth.transferFrom(weth_liquidity, gov, Wei("10000 ether"), {"from": weth_liquidity})

        # config yvCRV3 vault.
        Vault = pm(config["dependencies"][0]).Vault
        yCRV3 = Vault.deploy({"from": gov})
        yCRV3.initialize(crv3, gov, rewards, "", "")
        yCRV3.setDepositLimit(Wei("1000000 ether"))


        strategy = guardian.deploy(Strategy3Poolv2, yCRV3, dai, threePool, crv3, crv, unirouter, weth, proxy, gauge)
        strategy.setStrategist(strategist)

        yCRV3.addStrategy(
            strategy, 10_000, 0, 0, {"from": gov}
        )

        #setup for crv3
        crv3.approve(gov, Wei("1000000 ether"), {"from": gov})
        crv3.transferFrom(gov, bob, Wei("1000 ether"), {"from": gov})
        crv3.transferFrom(gov, alice, Wei("4000 ether"), {"from": gov})
        crv3.transferFrom(gov, tinytim, Wei("10 ether"), {"from": gov})
        crv3.approve(yCRV3, Wei("1000000 ether"), {"from": bob})
        crv3.approve(yCRV3, Wei("1000000 ether"), {"from": alice})
        crv3.approve(yCRV3, Wei("1000000 ether"), {"from": tinytim})
        #setup for dai
        dai.approve(gov, Wei("1000000 ether"), {"from": gov})
        dai.approve(threePool, Wei("1000000 ether"), {"from": gov})
        dai.approve(threePool, Wei("1000000 ether"), {"from": strategy})
        #setup for crv
        crv.approve(gov, Wei("1000000 ether"), {"from": gov})
        #setup for weth
        weth.approve(gov, Wei("1000000 ether"), {"from": gov})


        proxy.approveStrategy(strategy, {"from": govProxy, "gas limit": 120000000})

        # users deposit to vault
        yCRV3.deposit(Wei("1000 ether"), {"from": bob})
        yCRV3.deposit(Wei("4000 ether"), {"from": alice})
        yCRV3.deposit(Wei("10 ether"), {"from": tinytim})

        chain.mine(1)

        assert crv3.balanceOf(yCRV3) > 1
        assert crv3.balanceOf(alice) == 0
        assert yCRV3.balanceOf(alice) > 0

        a = yCRV3.pricePerShare()

        strategy.harvest({"from": gov})
        chain.mine(10)

        crv3.transferFrom(gov, yCRV3, Wei("1000 ether"), {"from": gov})
        strategy.harvest({"from": gov})
        chain.mine(10)

        assert crv3.balanceOf(strategy) == 0

        # there's already crv3 from the existing strategy. It will be counted as profit.
        b = yCRV3.pricePerShare()

        assert b > a

        #crv sent to strategy to mimic profit
        crv.transferFrom(gov, strategy, Wei("10000 ether"), {"from": gov})
        chain.mine(1)
        strategy.harvest({"from": gov})
        chain.mine(1)
        #second harvest to move crv3 back to strategy and increase strat debt
        strategy.harvest({"from": gov})
        chain.mine(1)

        assert crv.balanceOf(strategy) == 0

        c = yCRV3.pricePerShare()

        assert c > b

        yCRV3.withdraw({"from": alice})

        assert crv3.balanceOf(alice) > 0
        assert crv3.balanceOf(strategy) == 0
        assert crv3.balanceOf(bob) == 0

        yCRV3.withdraw({"from": bob})

        assert crv3.balanceOf(bob) > 0
        assert crv3.balanceOf(strategy) == 0

        yCRV3.withdraw({"from": tinytim})

        assert crv3.balanceOf(tinytim) > 0
        assert crv3.balanceOf(strategy) == 0

        pass

        ##crv3.transferFrom(gov, bob, Wei("100000 ether"), {"from": gov})
        ##crv3.transferFrom(gov, alice, Wei("788000 ether"), {"from": gov})

        # yUSDT.deposit(Wei("100000 ether"), {"from": bob})
        # yUSDT.deposit(Wei("788000 ether"), {"from": alice})

        # strategy.harvest()

        # assert dai.balanceOf(strategy) == 0
        # assert yUSDT3.balanceOf(strategy) > 0
        # assert ycrv3.balanceOf(strategy) > 0
