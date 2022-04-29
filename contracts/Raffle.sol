// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@chainlink/contracts/src/v0.8/VRFConsumerBase.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// A `Raffle` is a smart contract that represents a ticketed lottery,
/// where participants can buy tickets at a given fixed price.
/// Each sold ticket has the same probabilities of being picked as winner,
/// therefore, buying more tickets increments the odds of winning the prize.
/// The prize is calculated based on the amount collected by sold tickets,
/// minus some predefined percentage, considered profits, that goes to a specific
/// beneficiary address, that is configured when creating the contract.
/// When the raffle is closed, the contract automatically picks a winner ticket
/// at random. Randomness is obtained by relying on a Chainlink's VRF node.
/// Once a winner ticket is picked, the buyer address of that ticket can
/// redeem the prize by calling a function on this smart contract.
/// This raffle works with a specific ERC-20 token that is determined when
/// deploying the contract. All amounts will be expressed in terms of such
/// token, using the number of decimals that the token specifies.
contract Raffle is VRFConsumerBase, Ownable {
    /// The amount of tokens that it costs to buy one ticket.
    uint256 public ticketPrice;

    /// The minimum ticket number (e.g. 1)
    uint256 public ticketMinNumber;

    /// The maximum ticket number (e.g. 200)
    uint256 public ticketMaxNumber;

    /// The address of the ERC-20 token contract which is used as currency for the raffle.
    address public tokenAddress;

    /// The address that can claim the collected profits from this raffle.
    address public beneficiaryAddress;

    /// A number between 0 and 100 that determines how much percentage
    /// of the gathered amount from the sold tickets goes to profits,
    /// and how much goes to the winner prize.
    /// For instance, for a `profitFactor` of 15, it means that 15% of the sales
    /// will be considered profits and can be claimed by `beneficiaryAddress`,
    /// whereas the remaining 85% goes to the prize and can be claimed
    /// by the winner of the raffle.
    uint8 public profitFactor;

    /// The current state of the raffle.
    /// 0 = `created` -> Default state when contract is deployed. Raffle is defined but tickets are not on sale yet.
    /// 1 = `sellingTickets` -> The raffle is open. Users can buy tickets.
    /// 2 = `salesFinished` -> The raffle is closed. Users can no longer buy tickets.
    /// 3 = `calculatingWinner` -> A draw is occurring. The contract is calculating a winner.
    /// 4 = `cancelled` -> The raffle has been cancelled for some reason. Users can claim refunds for any tickets they have bought.
    /// 5 = `finished` -> The raffle has finished and there is a winner. The winner can redeem the prize.
    enum RaffleState {
        created,
        sellingTickets,
        salesFinished,
        calculatingWinner,
        cancelled,
        finished
    }
    RaffleState public currentState = RaffleState.created;

    /// Maps each ticket number to the address that bought that ticket.
    mapping(uint256 => address) public ticketAddress;

    /// Maps each address to the total amount spent in tickets by that address.
    mapping(address => uint256) public addressSpentAmount;

    /// The list of ticket numbers that have been sold.
    /// They are stored in the order that they were sold.
    uint256[] public soldTickets;

    /// A value that identifies unequivocally the Chainlink's VRF node.
    bytes32 public vrfKeyHash;

    /// The amount of LINK required as gas to get a random number from Chainlink's VRF, with 18 decimals.
    uint256 public vrfLinkFee;

    /// The address of the LINK token used to pay for VRF randomness requests.
    address public vrfLinkToken;

    /// The random number that was obtained from Chainlink's VRF.
    /// -1 if random number has not been obtained yet.
    int256 public obtainedRandomNumber = -1;

    /// The winner ticket number that was picked.
    /// -1 if winner ticket has not been picked yet.
    int256 public winnerTicketNumber = -1;

    /// The address that bought the winner ticket, who can claim the prize.
    address public winnerAddress;

    /// Whether or not the prize has been transferred to the winner.
    bool public prizeTransferred;

    /// Whether or not the profits have been transferred to the beneficiary.
    bool public profitsTransferred;

    ////////////////////////////////////////////////////////////
    // EVENTS
    ////////////////////////////////////////////////////////////

    /// Triggered when this contract requests a random number from Chainlink's VRF.
    event RequestedRandomness(bytes32 requestId);

    /// Triggered when the tickets sale is opened.
    event OpenedTicketsSale();

    /// Triggered when the tickets sale is closed.
    event ClosedTicketsSale();

    /// Triggered when a ticket is sold.
    event TicketSold(address buyer, uint256 ticketNumber);

    /// Triggered when the contract has picked a winner.
    event ObtainedWinner(address winnerAddress, uint256 winnerTicketNumber);

    /// Triggered when prize funds have been transferred to the winner.
    event PrizeTransferred(address recipient, uint256 amount);

    /// Triggered when profits have been transferred to the beneficiary.
    event ProfitsTransferred(address recipient, uint256 amount);

    /// Triggered when a refund has been transferred to the claimer.
    event RefundsTransferred(address recipient, uint256 amount);

    /// Triggered when the raffle is cancelled by the owner.
    event RaffleCancelled();

    ////////////////////////////////////////////////////////////
    // PUBLIC FUNCTIONS
    ////////////////////////////////////////////////////////////

    /// Buys a ticket for the caller, specified by `_ticketNumber`.
    function buyTicket(uint256 _ticketNumber)
        public
        onlyWhenAt(RaffleState.sellingTickets)
    {
        address buyer = msg.sender;
        require(
            _ticketNumber >= ticketMinNumber &&
                _ticketNumber <= ticketMaxNumber,
            "Invalid ticket number"
        );
        require(
            ticketAddress[_ticketNumber] == address(0),
            "Ticket number not available"
        );
        require(
            IERC20(tokenAddress).balanceOf(buyer) >= ticketPrice,
            "This address doesn't have enough balance to buy a ticket"
        );
        IERC20(tokenAddress).transferFrom(buyer, address(this), ticketPrice);
        ticketAddress[_ticketNumber] = buyer;
        addressSpentAmount[buyer] += ticketPrice;
        soldTickets.push(_ticketNumber);
        emit TicketSold(buyer, _ticketNumber);
    }

    /// Returns the current amount of tokens that the winner will obtain
    /// from this raffle.
    function getCurrentPrizeAmount() public view returns (uint256) {
        return getTotalAccumulatedAmount() - getCurrentProfitsAmount();
    }

    /// Returns the current amount of tokens that the beneficiary will obtain
    /// from this raffle in the concept of profit.
    function getCurrentProfitsAmount() public view returns (uint256) {
        return (getTotalAccumulatedAmount() * profitFactor) / 100;
    }

    /// Returns the total accumulated amounts provided by sold tickets.
    function getTotalAccumulatedAmount() public view returns (uint256) {
        return soldTickets.length * ticketPrice;
    }

    /// Returns the amount that can be returned in refunds to the caller.
    /// Refunds are only available if the caller has bought tickets and
    /// the raffle got cancelled.
    function getRefundableAmount() public view returns (uint256) {
        if (currentState != RaffleState.cancelled) {
            return 0;
        }
        return addressSpentAmount[msg.sender];
    }

    /// Claims refunds. If the caller has bought tickets and
    /// the raffle got cancelled, the total amount they spent will be
    /// returned to their account when executing this transaction.
    function claimRefunds() public {
        address recipient = msg.sender;
        uint256 amount = getRefundableAmount();
        require(amount > 0, "This address doesn't have a refundable amount");
        addressSpentAmount[recipient] = 0;
        IERC20(tokenAddress).transfer(recipient, amount);
        emit RefundsTransferred(recipient, amount);
    }

    ////////////////////////////////////////////////////////////
    // WINNER
    ////////////////////////////////////////////////////////////

    /// Redeems the raffle prize. If the caller has won the raffle,
    /// the prize amount will get transferred to their address.
    function redeemPrize()
        public
        onlyWinner
        onlyWhenAt(RaffleState.finished)
        onlyIfPrizeNotYetTransferred
    {
        address recipient = msg.sender;
        uint256 amount = getCurrentPrizeAmount();
        prizeTransferred = true;
        IERC20(tokenAddress).transfer(recipient, amount);
        emit PrizeTransferred(recipient, amount);
    }

    ////////////////////////////////////////////////////////////
    // BENEFICIARY
    ////////////////////////////////////////////////////////////

    function claimProfits()
        public
        onlyBeneficiary
        onlyWhenAt(RaffleState.finished)
        onlyIfProfitsNotYetTransferred
    {
        address recipient = msg.sender;
        uint256 amount = getCurrentProfitsAmount();
        profitsTransferred = true;
        IERC20(tokenAddress).transfer(recipient, amount);
        emit ProfitsTransferred(recipient, amount);
    }

    ////////////////////////////////////////////////////////////
    // OWNER
    ////////////////////////////////////////////////////////////

    constructor(
        address _tokenAddress,
        uint256 _ticketPrice,
        uint256 _ticketMinNumber,
        uint256 _ticketMaxNumber,
        uint8 _profitFactor,
        address _beneficiaryAddress,
        address _vrfCoordinator,
        bytes32 _vrfKeyHash,
        uint256 _vrfLinkFee,
        address _vrfLinkToken
    ) VRFConsumerBase(_vrfCoordinator, _vrfLinkToken) {
        require(
            _ticketMinNumber <= _ticketMaxNumber,
            "_ticketMaxNumber must be greater than _ticketMinNumber"
        );
        require(
            _profitFactor >= 0 && _profitFactor <= 100,
            "_profitFactor must be between 0 and 100"
        );
        tokenAddress = _tokenAddress;
        ticketPrice = _ticketPrice;
        ticketMinNumber = _ticketMinNumber;
        ticketMaxNumber = _ticketMaxNumber;
        profitFactor = _profitFactor;
        beneficiaryAddress = _beneficiaryAddress;
        vrfKeyHash = _vrfKeyHash;
        vrfLinkFee = _vrfLinkFee;
        vrfLinkToken = _vrfLinkToken;
    }

    /// Opens the raffle so participants can start buying tickets.
    function openTicketsSale()
        public
        onlyOwner
        onlyWhenAt(RaffleState.created)
    {
        currentState = RaffleState.sellingTickets;
        emit OpenedTicketsSale();
    }

    /// Closes the raffle so participants cannot buy any more tickets.
    function closeTicketsSale()
        public
        onlyOwner
        onlyWhenAt(RaffleState.sellingTickets)
    {
        currentState = RaffleState.salesFinished;
        emit ClosedTicketsSale();
    }

    /// Closes the raffle so participants cannot buy any more tickets,
    /// and also starts calcuilating a winner.
    function closeTicketsSaleAndPickWinner()
        public
        onlyOwner
        onlyWhenAt(RaffleState.sellingTickets)
    {
        closeTicketsSale();
        pickWinner();
    }

    /// Starts calculating a winner.
    function pickWinner()
        public
        onlyOwner
        onlyWhenAt(RaffleState.salesFinished)
    {
        currentState = RaffleState.calculatingWinner;
        _requestRandomNumberToPickWinner();
    }

    /// Cancels the raffle.
    function cancelRaffle()
        public
        onlyOwner
        onlyBefore(RaffleState.calculatingWinner)
    {
        currentState = RaffleState.cancelled;
        emit RaffleCancelled();
    }

    ////////////////////////////////////////////////////////////
    // Private / Internal
    ////////////////////////////////////////////////////////////

    /// Requests a random number from Chainlink's VRF in order to pick the winner ticket.
    function _requestRandomNumberToPickWinner() private returns (uint256) {
        require(
            IERC20(vrfLinkToken).balanceOf(address(this)) >= vrfLinkFee,
            "This contract doesn't have enough LINK to request randomness from Chainlink's VRF"
        );
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

        obtainedRandomNumber = int256(_randomness);

        uint256 winnerTicketIndex = _randomness % soldTickets.length;
        winnerTicketNumber = int256(soldTickets[winnerTicketIndex]);
        winnerAddress = ticketAddress[uint256(winnerTicketNumber)];
        require(winnerAddress != address(0), "Cannot find a winner");

        currentState = RaffleState.finished;
        emit ObtainedWinner(winnerAddress, uint256(winnerTicketNumber));
    }

    modifier onlyWhenAt(RaffleState _state) {
        require(currentState == _state, "Invalid state");
        _;
    }

    modifier onlyBefore(RaffleState _state) {
        require(currentState < _state, "Invalid state");
        _;
    }

    modifier onlyWinner() {
        require(
            msg.sender == winnerAddress,
            "Only the raffle winner can execute this function"
        );
        _;
    }

    modifier onlyBeneficiary() {
        require(
            msg.sender == beneficiaryAddress,
            "Only the raffle beneficiary can execute this function"
        );
        _;
    }

    modifier onlyIfPrizeNotYetTransferred() {
        require(
            prizeTransferred == false,
            "The prize has already been transferred"
        );
        _;
    }

    modifier onlyIfProfitsNotYetTransferred() {
        require(
            profitsTransferred == false,
            "Profits have already been transferred"
        );
        _;
    }
}
