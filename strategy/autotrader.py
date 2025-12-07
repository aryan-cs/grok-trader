class Strategy:
    def __init__(self, market_slug):
        pass

    def on_new_post(self, tweet):
        # Trigger grok research. Provide the last 10 unique tweets and their timestamps, as well as the state of the book.
        # Ask for a trading decision. If "yes", send a buy order for yes. If "no" send a buy order for no. Both should be IOC.
        pass

    def on_new_book(self, book):
        # Update the local book snapshot for this market
        # Store the book as a class variable
        print(book)
