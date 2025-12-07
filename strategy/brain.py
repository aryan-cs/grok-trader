class IOCDecision:
    # represents to buy a yes or no market at some price at some size. only buys and IOC orders.
    def __init__(
        self,
        side,
        price,
        size,
    ):
        pass


def produce_trading_decision(max_size, condition, yes_book, no_book, tweet_window):
    # ask grok 4.1 reasoning fast for trading decision w/ view of last 10 relevant tweets and state of books
    # tell it to use the X API search functionality and web search functionality
    # parse this into an IOCDecision with structured outputs
    pass
