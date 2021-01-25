// SPDX-License-Identifier: MIT

pragma experimental ABIEncoderV2;
pragma solidity 0.6.12;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/math/SafeMath.sol";
import "@openzeppelin/contracts/math/Math.sol";
import "@openzeppelin/contracts/utils/Address.sol";
import "@openzeppelin/contracts/token/ERC20/SafeERC20.sol";
import {BaseStrategy, StrategyParams} from "@yearnvaults/contracts/BaseStrategy.sol";

import "../../interfaces/curve/ICurve.sol";
import "../../interfaces/curve/VoterProxy.sol";
import "../../interfaces/uniswap/Uni.sol";
import "../../interfaces/yearn/Vault.sol";


contract Strategy3Pool2 is BaseStrategy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;

    address public dai;
    address public threePool;
    address public crv3;
    address public crv;
    address public unirouter;
    address public weth;
    string public constant override name = "Strategy3Pool2";

    address public proxy;
    address public voter;
    address public gauge;

    // adding protection against slippage attacks
    uint constant public DENOMINATOR = 10000;
    uint public slip = 100;

    constructor(
        address _vault,
        address _dai,
        address _threePool,
        address _crv3,
        address _crv,
        address _unirouter,
        address _weth,
        address _proxy,
        address _gauge
    ) public BaseStrategy(_vault) {
        dai = _dai;
        threePool = _threePool;
        crv3 = _crv3;
        crv = _crv;
        unirouter = _unirouter;
        weth = _weth;
        proxy = _proxy;
        gauge = _gauge;

        //crv3 is want
        IERC20(dai).safeApprove(threePool, uint256(-1));
        IERC20(crv).safeApprove(unirouter, uint256(-1));
        IERC20(weth).safeApprove(unirouter, uint256(-1));
        want.safeApprove(proxy, uint256(-1));
    }

    function protectedTokens() internal override view returns (address[] memory) {
        address[] memory protected = new address[](3);
        // crv3 (aka want) is already protected by default
        protected[0] = crv;
        protected[1] = weth;
        protected[2] = dai;
        return protected;
    }

    // returns sum of all assets, realized and unrealized
    function estimatedTotalAssets() public override view returns (uint256) {
        return balanceOfWant().add(balanceOfPool());
    }

    function prepareReturn(uint256 _debtOutstanding) internal override returns (uint256 _profit, uint256 _loss, uint256 _debtPayment) {
       // We might need to return want to the vault
        if (_debtOutstanding > 0) {
           uint256 _amountFreed = 0;
           (_amountFreed, _loss) = liquidatePosition(_debtOutstanding);
           _debtPayment = Math.min(_amountFreed, _debtOutstanding);
        }

        // harvest() will track profit by estimated total assets compared to debt.
        uint256 balanceOfWantBefore = balanceOfWant();
        uint256 debt = vault.strategies(address(this)).totalDebt;
        uint256 currentValue = estimatedTotalAssets();

        VoterProxy(proxy).harvest(gauge);
        uint256 _crvBalance = IERC20(crv).balanceOf(address(this));
        _swapCRV(_crvBalance);
        uint256 _daiBalance = IERC20(dai).balanceOf(address(this));
        _swapDAI(_daiBalance);

        uint256 balanceOfWantAfter = balanceOfWant();

        if (balanceOfWantAfter > balanceOfWantBefore) {
            _profit = balanceOfWantAfter.sub(balanceOfWantBefore);
        }
        else {_profit == 0;}

        if (debt > currentValue) {
            _loss == debt.sub(currentValue);
        }
        else {_loss == 0;}
    }

    function adjustPosition(uint256 _debtOutstanding) internal override {
       //emergency exit is dealt with in prepareReturn
        if (emergencyExit) {
          return;
       }

        // do not invest if we have more debt than want
        if (_debtOutstanding > balanceOfWant()) {
            return;
        }

       // Invest the rest of the want
       uint256 _wantAvailable = balanceOfWant().sub(_debtOutstanding);
        if (_wantAvailable > 0) {
            uint256 _availableFunds = want.balanceOf(address(this));
            //uint256 v = _availableFunds.mul(1e18).div(ICurve(threePool).get_virtual_price());
            //ICurve(threePool).add_liquidity([_availableFunds,0,0], v.mul(DENOMINATOR.sub(slip)).div(DENOMINATOR));
            want.safeTransfer(proxy, _availableFunds);
            VoterProxy(proxy).deposit(gauge, address(want));
        }
    }

    //v0.3.0 - liquidatePosition is emergency exit. Supplants exitPosition
    function liquidatePosition(uint256 _amountNeeded) internal override returns (uint256 _liquidatedAmount, uint256 _loss) {
        if (balanceOfWant() < _amountNeeded) {
            // We need to withdraw to get back more want
            _withdrawSome(_amountNeeded.sub(balanceOfWant()));
        }

        uint256 balanceOfWant = balanceOfWant();

        if (balanceOfWant >= _amountNeeded) {
            _liquidatedAmount = _amountNeeded;
        } else {
            _liquidatedAmount = balanceOfWant;
            _loss = (_amountNeeded.sub(balanceOfWant));
        }
    }

    // withdraw some want from the gauge
    function _withdrawSome(uint256 _amount) internal returns (uint256) {
        uint256 balanceOfWantBefore = balanceOfWant();
        //uint256 proxyAmount = VoterProxy(proxy).balanceOf(gauge);
        VoterProxy(proxy).withdraw(gauge, address(want), _amount);
        uint256 balanceAfter = balanceOfWant();
        return balanceAfter.sub(balanceOfWantBefore);
    }

    // it looks like this function transfers not just "want" tokens, but all tokens
    function prepareMigration(address _newStrategy) internal override {
        withdrawProxy();
        // want is transferred by the base contract's migrate function
        // in truth only the want token should be transferred. DAI, crv, weth are all intermediates and should be zero
        IERC20(dai).transfer(_newStrategy, IERC20(dai).balanceOf(address(this)));
        IERC20(crv).transfer(_newStrategy, IERC20(crv).balanceOf(address(this)));
        IERC20(weth).transfer(_newStrategy, IERC20(weth).balanceOf(address(this)));
    }

    // returns value of total crv3 in gauge
    function balanceOfPool() public view returns (uint256) {
        uint256 _balance = VoterProxy(proxy).balanceOf(gauge);
        return (_balance); //to the force
    }

    // returns balance of crv3
    function balanceOfWant() public view returns (uint256) {
        return want.balanceOf(address(this));
    }

    function setSlip(uint _slip) external {
        require(msg.sender == strategist || msg.sender == governance(), "!sg");
        slip = _slip;
    }

    function setProxy(address _proxy) external {
        require(msg.sender == strategist || msg.sender == governance(), "!sg");
        proxy = _proxy;
    }

    // withdraw all from proxy
    function withdrawProxy() internal {
        VoterProxy(proxy).withdrawAll(gauge, address(want));
    }

    function _swapCRV(uint256 _amountIn) internal returns (uint256[] memory amounts) {
        address[] memory path = new address[](3);
        path[0] = address(0xD533a949740bb3306d119CC777fa900bA034cd52); // crv
        path[1] = address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2); // weth
        path[2] = address(0x6B175474E89094C44Da98b954EedeAC495271d0F); // dai

        Uni(unirouter).swapExactTokensForTokens(_amountIn, uint256(0), path, address(this), now);
    }


    function _swapDAI(uint256 _amountIn) internal returns(uint256) {
        uint256 v = _amountIn.mul(1e18).div(ICurve(threePool).get_virtual_price());
        ICurve(threePool).add_liquidity([_amountIn,0,0], v.mul(DENOMINATOR.sub(slip)).div(DENOMINATOR));
        uint256 _crv3Balance = IERC20(crv3).balanceOf(address(this));
        return _crv3Balance;
    }
}

