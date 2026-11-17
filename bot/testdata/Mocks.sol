// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Test doubles for live-mode tests: fixed exchange rate, no real pools.
contract MockToken {
    string public name = "Mock"; string public symbol = "MOCK"; uint8 public decimals = 18;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    constructor() { balanceOf[msg.sender] = 1e30; }
    function transfer(address to, uint256 v) external returns (bool) { balanceOf[msg.sender] -= v; balanceOf[to] += v; return true; }
    function approve(address s, uint256 v) external returns (bool) { allowance[msg.sender][s] = v; return true; }
    function transferFrom(address f, address to, uint256 v) external returns (bool) {
        allowance[f][msg.sender] -= v; balanceOf[f] -= v; balanceOf[to] += v; return true;
    }
}

interface IToken { function transfer(address, uint256) external returns (bool); function transferFrom(address, address, uint256) external returns (bool); }

contract MockV2Router {
    address public weth; uint256 public rate; // tokens per 1 ETH
    constructor(address _weth, uint256 _rate) payable { weth = _weth; rate = _rate; }
    receive() external payable {}
    function getAmountsOut(uint256 amountIn, address[] calldata path) external view returns (uint256[] memory amounts) {
        amounts = new uint256[](2); amounts[0] = amountIn;
        amounts[1] = path[0] == weth ? amountIn * rate : amountIn / rate;
    }
    function swapExactETHForTokensSupportingFeeOnTransferTokens(uint256 amountOutMin, address[] calldata path, address to, uint256 deadline) external payable {
        require(block.timestamp <= deadline, "EXPIRED"); require(path[0] == weth, "PATH");
        uint256 out = msg.value * rate; require(out >= amountOutMin, "INSUFFICIENT_OUTPUT_AMOUNT");
        IToken(path[1]).transfer(to, out);
    }
    function swapExactTokensForETHSupportingFeeOnTransferTokens(uint256 amountIn, uint256 amountOutMin, address[] calldata path, address to, uint256 deadline) external {
        require(block.timestamp <= deadline, "EXPIRED"); require(path[1] == weth, "PATH");
        IToken(path[0]).transferFrom(msg.sender, address(this), amountIn);
        uint256 out = amountIn / rate; require(out >= amountOutMin, "INSUFFICIENT_OUTPUT_AMOUNT");
        payable(to).transfer(out);
    }
}

// Mimics SwapRouter02 + QuoterV2 in one contract. Only the 500 and 3000 fee pools exist.
contract MockV3 {
    struct ExactInputSingleParams { address tokenIn; address tokenOut; uint24 fee; address recipient; uint256 amountIn; uint256 amountOutMinimum; uint160 sqrtPriceLimitX96; }
    struct QuoteParams { address tokenIn; address tokenOut; uint256 amountIn; uint24 fee; uint160 sqrtPriceLimitX96; }
    address public weth; uint256 public rate; uint256 private wrapped; // "WETH" held by the router
    constructor(address _weth, uint256 _rate) payable { weth = _weth; rate = _rate; }
    receive() external payable {}
    function _rate(uint24 fee) internal view returns (uint256) {
        require(fee == 500 || fee == 3000, "NO_POOL");
        return fee == 500 ? rate : rate * 98 / 100; // the 0.05 % pool gives a better rate
    }
    function quoteExactInputSingle(QuoteParams memory p) external returns (uint256 amountOut, uint160, uint32, uint256) {
        uint256 r = _rate(p.fee);
        amountOut = p.tokenIn == weth ? p.amountIn * r : p.amountIn / r;
        return (amountOut, 0, 0, 100000);
    }
    function multicall(uint256 deadline, bytes[] calldata data) external payable returns (bytes[] memory results) {
        require(block.timestamp <= deadline, "Transaction too old");
        results = new bytes[](data.length);
        for (uint256 i = 0; i < data.length; i++) {
            (bool ok, bytes memory res) = address(this).delegatecall(data[i]);
            if (!ok) { assembly { revert(add(res, 32), mload(res)) } }
            results[i] = res;
        }
    }
    function exactInputSingle(ExactInputSingleParams calldata p) external payable returns (uint256 amountOut) {
        uint256 r = _rate(p.fee);
        if (p.tokenIn == weth) {
            require(msg.value == p.amountIn, "VALUE");
            amountOut = p.amountIn * r; require(amountOut >= p.amountOutMinimum, "Too little received");
            IToken(p.tokenOut).transfer(p.recipient, amountOut);
        } else {
            IToken(p.tokenIn).transferFrom(msg.sender, address(this), p.amountIn);
            amountOut = p.amountIn / r; require(amountOut >= p.amountOutMinimum, "Too little received");
            require(p.recipient == address(2), "RECIPIENT"); // ADDRESS_THIS: WETH stays on the router until unwrap
            wrapped += amountOut;
        }
    }
    function unwrapWETH9(uint256 amountMinimum, address recipient) external payable {
        uint256 amount = wrapped; require(amount >= amountMinimum, "Insufficient WETH9");
        wrapped = 0; payable(recipient).transfer(amount);
    }
}

// Same aggregate3 and getEthBalance as the real Multicall3 (0xcA11...), enough for prices and balances.
contract MockMulticall {
    struct Call3 { address target; bool allowFailure; bytes callData; }
    struct Result { bool success; bytes returnData; }
    function aggregate3(Call3[] calldata calls) external payable returns (Result[] memory results) {
        results = new Result[](calls.length);
        for (uint256 i = 0; i < calls.length; i++) {
            (bool ok, bytes memory data) = calls[i].target.call(calls[i].callData);
            require(ok || calls[i].allowFailure, "Multicall3: call failed");
            results[i] = Result(ok, data);
        }
    }
    function getEthBalance(address addr) external view returns (uint256) { return addr.balance; }
}
