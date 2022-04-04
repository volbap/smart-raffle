// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@chainlink/contracts/src/v0.8/VRFConsumerBase.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// A `RaffleManager` is a smart contract that allows to create raffles
/// where participants can buy tickets and have their chances of winning
/// the total accumulated amount of the raffle.
/// This contract only allows managing one raffle at a time.
contract RaffleManager is VRFConsumerBase, Ownable {
    /// The price that it costs to buy one ticket, in USDC, with 6 decimals.
    uint256 public ticketPrice;

    /// The minimum ticket number (e.g. 1)
    uint256 public ticketMinNumber;

    /// The maximum ticket number (e.g. 200)
    uint256 public ticketMaxNumber;

    /// The address of the USDC token contract, which is used as currency for the raffle.
    address public usdcToken;

    /// The current state of the raffle.
    /// 0 = `closed` -> Default state. There are no ongoing raffles.
    /// 1 = `open` -> There is an ongoing raffle and users can buy tickets.
    /// 2 = `calculatingWinner` -> A raffle has recently finished and the contract is calculating a winner.
    enum RaffleState {
        closed,
        open,
        calculatingWinner
    }
    RaffleState public currentState = RaffleState.closed;

    /// An event that is triggered when this contract requests a random number from Chainlink's VRF.
    event RequestedRandomness(bytes32 requestId);

    /// The amount of LINK required as gas to get a random number from Chainlink's VRF, with 18 decimals.
    uint256 public vrfLinkFee;

    /// A value that identifies unequivocally the Chainlink's VRF node.
    bytes32 public vrfKeyHash;

    /// The last random number that was obtained from Chainlink's VRF.
    uint256 public lastRandomNumber;

    /// The last winner ticket number that was picked.
    uint256 public lastWinnerTicket;

    /// The address that bought the last winner ticket number.
    address public lastWinnerAddress;

    /// Maps each ticket number to the address that bought that ticket.
    mapping(uint256 => address) public ticketAddresses;

    /// The list of tickets that have been sold, in the order that they were sold.
    // TODO: Convert to mapping (uint256 => bool).
    // Probably requires a separate variable to track `soldTicketsCount`.
    // maybe it's convenient to use `ticketAddresses` directly.
    uint256[] soldTickets;

    /// Maps addresses to the amount of USDC earned in prizes, using 6 decimals.
    mapping(address => uint256) public addressToPrizeAmount;

    constructor(
        address _usdcToken,
        address _vrfCoordinator,
        uint256 _vrfLinkFee,
        bytes32 _vrfKeyHash,
        address _linkToken
    ) VRFConsumerBase(_vrfCoordinator, _linkToken) {
        usdcToken = _usdcToken;
        vrfLinkFee = _vrfLinkFee;
        vrfKeyHash = _vrfKeyHash;
    }

    /// Buys one ticket for the caller, specified by `_ticketNumber`.
    function buyTicket(uint256 _ticketNumber) public {
        require(currentState == RaffleState.open, "Raffle has not started yet");
        require(
            _ticketNumber >= ticketMinNumber &&
                _ticketNumber <= ticketMaxNumber,
            "Invalid ticket number"
        );
        require(
            ticketAddresses[_ticketNumber] == address(0),
            "Ticket number not available"
        );
        IERC20(usdcToken).transferFrom(msg.sender, address(this), ticketPrice);
        ticketAddresses[_ticketNumber] = msg.sender;
        soldTickets.push(_ticketNumber);
    }

    /// Returns the current prize for the ongoing raffle.
    /// The prize is calculated by summing the value of all the tickets
    /// that have been sold.
    /// Amount returned is represented in USDC with 6 decimals.
    function getCurrentPrizeAmount() public view returns (uint256) {
        return soldTickets.length * ticketPrice;
    }

    /// Claims the amount won by the caller in closed raffles.
    /// If the caller has won raffles, the total amount won
    /// will get transferred to them.
    function redeemPrize() public {
        require(
            addressToPrizeAmount[msg.sender] > 0,
            "There is no prize for this address"
        );
        IERC20(usdcToken).transfer(
            msg.sender,
            addressToPrizeAmount[msg.sender]
        );
    }

    /// Opens a new raffle so participants can start buying tickets.
    function openRaffle(
        uint256 _ticketPrice,
        uint256 _ticketMinNumber,
        uint256 _ticketMaxNumber
    ) public onlyOwner {
        require(
            currentState == RaffleState.closed,
            "There is raffle in progress already. Can't open a new raffle"
        );
        require(_ticketMinNumber >= 0, "_ticketMinNumber cannot be negative");
        require(
            _ticketMinNumber <= _ticketMaxNumber,
            "_ticketMaxNumber must be greater than _ticketMinNumber"
        );
        require(
            _ticketMaxNumber <= type(uint256).max,
            "_ticketMaxNumber is too high"
        );
        require(_ticketPrice > 0, "_ticketPrice cannot be negative");
        require(_ticketPrice <= type(uint256).max, "_ticketPrice is too high");
        ticketPrice = _ticketPrice;
        ticketMinNumber = _ticketMinNumber;
        ticketMaxNumber = _ticketMaxNumber;
        currentState = RaffleState.open;
    }

    /// Closes the current raffle and starts calculating the winner ticket.
    /// Once calculated, the winner ticket will be stored in `_lastWinnerTicket`.
    /// At that point, the address who bought that ticket can claim the funds
    /// of that raffle using the function `redeemPrize`.
    function closeRaffle() public onlyOwner {
        require(
            currentState == RaffleState.open,
            "There isn't any ongoing raffle to close"
        );
        currentState = RaffleState.calculatingWinner;
        startCalculatingWinner();
    }

    /// Starts calculating the winner ticket.
    function startCalculatingWinner() private returns (uint256) {
        // We'll connect to the Chainlink VRF Node
        // using the "Request and Receive" cycle model

        // R&R -> 2 transactions:
        // 1) Request the data from the Chainlink Oracle through a function (requestRandomness)
        // 2) Callback transaction -> Chainlink node returns data to the contract into another function (fulfillRandomness)

        // requestRandomness function is provided by VRFConsumerBase parent class
        bytes32 requestId = requestRandomness(vrfKeyHash, vrfLinkFee);

        // We emit the following event to be able to retrieve the requestId in the tests.
        // Also, events work as logs for the contract.
        emit RequestedRandomness(requestId);
    }

    // We need to override fulfillRandomness from VRFConsumerBase in order to retrieve the random number.
    // This function will be called for us by the VRFCoordinator (that's why it's internal).
    // This function works asynchronously.
    function fulfillRandomness(bytes32 _requestId, uint256 _randomness)
        internal
        override
    {
        require(
            currentState == RaffleState.calculatingWinner,
            "Raffle is not calculating winners yet"
        );
        require(_randomness > 0, "Random number not found");

        lastRandomNumber = _randomness;

        uint256 winnerTicketIndex = _randomness % soldTickets.length;
        uint256 winnerTicketNumber = soldTickets[winnerTicketIndex];
        lastWinnerTicket = winnerTicketNumber;

        address winnerAddress = ticketAddresses[winnerTicketNumber];
        lastWinnerAddress = winnerAddress;
        require(winnerAddress != address(0), "Cannot find a winner");

        addressToPrizeAmount[winnerAddress] += getCurrentPrizeAmount(); // test +=

        resetRaffle();
    }

    /// Resets state. Private usage only.
    function resetRaffle() private {
        resetTicketAddressesMapping();
        soldTickets = new uint256[](0);
        currentState = RaffleState.closed;
    }

    function resetTicketAddressesMapping() private {
        for (
            uint256 number = ticketMinNumber;
            number <= ticketMaxNumber;
            number++
        ) {
            ticketAddresses[number] = address(0);
        }
    }
}
