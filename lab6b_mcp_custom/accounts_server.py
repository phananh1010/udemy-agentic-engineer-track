from mcp.server.fastmcp import FastMCP
from .accounts import Account


mcp = FastMCP("accounts_server")

@mcp.tool()
async def get_balance(name: str) -> float: 
    """Get the cash balance of the given accont name
        args: 
            name: name of the account holder
    """
    return Account.get(name).balance


@mcp.tool()
async def get_holdings(name: str) -> dict[str, int]:
    """Get holdings of the given account name
    
    Args: 
        name: the name of the account holder
    """
    return Account.get(name).holdings

@mcp.tool()
async def buy_shares(name: str, symbol: str, quantity: int, rationale: str) -> float:
    """Buy shares of a stock
    Args: 
        name: name of account holder
        symbol: symbol of the stock
        quantity: the quantity of shares to buy
        rationale: rationale of the purchase and fit with account strategy
    """
    return Account.get(name).buy_shares(symbol, quantity, rationale)

@mcp.tool()
async def sell_shares(name: str, symbol: str, quantity: int, rationale: str) -> float:
    """Sell a share of a stock
    
    Args: 
        name: name of account holder
        symbol: symbol of the stock
        quantity: the quantity of shares to sell
        rationale: rationale of the sale and fit with account strategy
    """
    return Account.get(name).sell_shares(symbol, quantity, rationale)

@mcp.tool()
async def change_strategy(name: str, strategy: str) -> str:
    """At your discretion, call this to change your investment stratgegy for the future
    Args: 
        name: name of account holder
        strategy: new strategy for the account
    """
    return Account.get(name).change_strategy(strategy)

@mcp.resource("accounts://accounts_server/{name}")
async def read_account_resource(name:str) -> str:
    account = Account.get(name)
    return account.report

@mcp.resource ("accounts://strategy/{name}")
async def read_account_strategy(name: str) -> str:
    account = Account.get(name.lower())
    return account.get_strategy()

if __name__ == "__main__":
    mcp.run(transport="stdio")