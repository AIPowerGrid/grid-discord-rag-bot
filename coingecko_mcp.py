"""
CoinGecko MCP client for fetching cryptocurrency data.
Connects to the CoinGecko MCP server and provides helper functions.
Falls back to CoinGecko REST API if MCP is unavailable.
"""

import os
import asyncio
import json
from typing import Optional, Dict, Any, List
from io import BytesIO
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import requests

# CoinGecko MCP server URL
COINGECKO_MCP_URL = "https://mcp.pro-api.coingecko.com/mcp"
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

async def get_coingecko_session() -> Optional[ClientSession]:
    """Get a CoinGecko MCP session for testing purposes."""
    try:
        headers = {
            "X-Cg-Pro-Api-Key": COINGECKO_API_KEY,
            "X-Cg-Demo-Api-Key": COINGECKO_API_KEY,
            "Authorization": f"Bearer {COINGECKO_API_KEY}",
        }
        
        async with streamablehttp_client(COINGECKO_MCP_URL, headers=headers) as (
            read_stream,
            write_stream,
            _,
        ):
            session = ClientSession(read_stream, write_stream)
            await session.initialize()
            return session
    except Exception as e:
        print(f"Error creating CoinGecko MCP session: {e}")
        return None


async def _call_coingecko_tool(tool_name: str, arguments: dict) -> Optional[Any]:
    """Helper to call a CoinGecko MCP tool with proper session management.
    Uses MCP as the primary method, per CoinGecko docs.
    Tries public server first, then authenticated server."""
    # Try public server first (no auth required)
    public_url = "https://mcp.api.coingecko.com/mcp"
    
    try:
        async with streamablehttp_client(public_url) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                
                # Call the tool
                result = await session.call_tool(tool_name, arguments)
                return result
    except Exception as e:
        # If public server fails, try authenticated server
        try:
            headers = {
                "X-Cg-Pro-Api-Key": COINGECKO_API_KEY,
                "X-Cg-Demo-Api-Key": COINGECKO_API_KEY,
                "Authorization": f"Bearer {COINGECKO_API_KEY}",
            }
            
            async with streamablehttp_client(COINGECKO_MCP_URL, headers=headers) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    
                    # Call the tool
                    result = await session.call_tool(tool_name, arguments)
                    return result
        except Exception as e2:
            # Suppress cleanup errors - they don't affect functionality
            error_str = str(e2)
            if "TaskGroup" in error_str or "unhandled errors" in error_str:
                # These are usually cleanup errors, not actual failures
                pass
            else:
                print(f"Error calling CoinGecko MCP tool {tool_name}: {e2}")
            return None


async def _get_price_via_api(coin_id: str) -> Optional[str]:
    """Fallback: Get price via CoinGecko REST API."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        headers = {
            "X-Cg-Demo-Api-Key": COINGECKO_API_KEY,
            "X-Cg-Pro-Api-Key": COINGECKO_API_KEY,
        }
        params = {
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if coin_id in data:
            price_info = data[coin_id]
            price = price_info.get("usd", 0)
            change_24h = price_info.get("usd_24h_change", 0)
            
            change_str = f" ({change_24h:+.2f}%)" if change_24h else ""
            # Format price with appropriate decimals - more for small prices
            if price < 0.01:
                price_str = f"${price:.6f}".rstrip('0').rstrip('.')
            elif price < 1:
                price_str = f"${price:.4f}".rstrip('0').rstrip('.')
            else:
                price_str = f"${price:,.2f}"
            return f"{coin_id}: {price_str}{change_str}"
        
        return None
    except Exception as e:
        print(f"Error fetching price via API fallback: {e}")
        return None


async def get_crypto_price(coin_id: str) -> Optional[str]:
    """Get current price for a cryptocurrency. Returns formatted string.
    Uses REST API directly for accurate, up-to-date prices (MCP can be stale)."""
    # Use REST API directly - MCP data can be stale
    return await _get_price_via_api(coin_id)


async def search_crypto(query: str) -> Optional[List[Dict[str, Any]]]:
    """Search for cryptocurrencies matching a query using natural language.
    Tries MCP first (get_search tool), falls back to REST API."""
    try:
        # Try MCP first - use the correct tool name: get_search
        try:
            result = await _call_coingecko_tool("get_search", {"query": query})
            if result:
                # Parse the result
                if hasattr(result, 'structuredContent') and result.structuredContent:
                    data = result.structuredContent
                    # The search endpoint returns: {"coins": [...], "exchanges": [...], "nfts": [...], "categories": [...]}
                    if isinstance(data, dict):
                        # Extract coins from the response
                        coins = data.get("coins", [])
                        if coins and isinstance(coins, list) and len(coins) > 0:
                            return coins
                    elif isinstance(data, list) and len(data) > 0:
                        # If it's already a list, return it
                        return data
                
                if result.content and len(result.content) > 0:
                    content = result.content[0]
                    if hasattr(content, 'text'):
                        # Try to parse as JSON
                        try:
                            data = json.loads(content.text)
                            # Handle structured response
                            if isinstance(data, dict):
                                coins = data.get("coins", [])
                                if coins and isinstance(coins, list) and len(coins) > 0:
                                    return coins
                            elif isinstance(data, list) and len(data) > 0:
                                return data
                        except:
                            pass
        except Exception as e:
            print(f"MCP search failed: {e}")
        
        # Fallback to REST API
        try:
            url = "https://api.coingecko.com/api/v3/search"
            headers = {
                "X-Cg-Demo-Api-Key": COINGECKO_API_KEY,
                "X-Cg-Pro-Api-Key": COINGECKO_API_KEY,
            }
            params = {"query": query}
            
            response = requests.get(url, headers=headers, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            # CoinGecko search returns: {"coins": [...], "exchanges": [...], "nfts": [...], "categories": [...]}
            if isinstance(data, dict):
                coins = data.get("coins", [])
                if coins and isinstance(coins, list) and len(coins) > 0:
                    return coins
            
            return None
        except Exception as e:
            print(f"REST API search failed: {e}")
            return None
        
    except Exception as e:
        print(f"Error searching crypto: {e}")
        return None


async def get_chart_data(coin_id: str, days: int = 7) -> Optional[Dict[str, Any]]:
    """Get market chart data for a cryptocurrency. Returns chart data or None.
    Tries MCP first, falls back to REST API."""
    try:
        from datetime import datetime, timedelta
        
        # Try MCP first
        try:
            to_date = datetime.now()
            from_date = to_date - timedelta(days=days)
            
            # Format dates as ISO strings
            from_iso = from_date.strftime("%Y-%m-%d")
            to_iso = to_date.strftime("%Y-%m-%d")
            
            # Try to get chart data via MCP
            tool_args = {
                "id": coin_id,
                "vs_currency": "usd",
                "from": from_iso,
                "to": to_iso,
                "interval": "daily" if days > 30 else "hourly"
            }
            
            result = await _call_coingecko_tool("get_range_coins_market_chart", tool_args)
            if result:
                # Parse chart data
                if result.content and len(result.content) > 0:
                    content = result.content[0]
                    if hasattr(content, 'text'):
                        try:
                            data = json.loads(content.text)
                            if data and "prices" in data:
                                return data
                        except:
                            pass
                
                if hasattr(result, 'structuredContent') and result.structuredContent:
                    data = result.structuredContent
                    if data and "prices" in data:
                        return data
        except Exception as e:
            print(f"MCP chart fetch failed: {e}")
        
        # Fallback to REST API
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
            params = {
                "vs_currency": "usd",
                "days": str(days)
            }
            headers = {
                "X-Cg-Demo-Api-Key": COINGECKO_API_KEY,
                "X-Cg-Pro-Api-Key": COINGECKO_API_KEY,
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data and "prices" in data:
                return data
        except Exception as e:
            print(f"REST API chart fetch failed: {e}")
        
        return None
    except Exception as e:
        print(f"Error fetching chart data: {e}")
        return None


async def get_ohlc_data(coin_id: str, days: int = 7) -> Optional[List[List[float]]]:
    """Get OHLC (candlestick) data for a cryptocurrency. Returns list of [timestamp, open, high, low, close].
    Uses REST API directly for OHLC data as it provides more reliable recent data."""
    try:
        # Use REST API directly for OHLC - MCP seems to return stale data
        # REST API provides more current hourly/daily candles
        try:
            # Strategy: Get hourly data for recent period (last 1 day) to ensure latest candles
            # Then combine with daily data for older period if needed
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
            headers = {
                "X-Cg-Demo-Api-Key": COINGECKO_API_KEY,
                "X-Cg-Pro-Api-Key": COINGECKO_API_KEY,
            }
            
            # Always get hourly data for the last 24 hours to ensure we have the most recent candle
            params_hourly = {"vs_currency": "usd", "days": "1"}
            response = requests.get(url, headers=headers, params=params_hourly, timeout=10)
            response.raise_for_status()
            hourly_data = response.json()
            
            if not isinstance(hourly_data, list) or len(hourly_data) == 0:
                # Fallback to requested days if hourly fails
                params = {"vs_currency": "usd", "days": str(days)}
                response = requests.get(url, headers=headers, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    return data
                return None
            
            # If we need more than 1 day, combine with daily data
            if days > 1:
                params_daily = {"vs_currency": "usd", "days": str(days)}
                response_daily = requests.get(url, headers=headers, params=params_daily, timeout=10)
                response_daily.raise_for_status()
                daily_data = response_daily.json()
                
                if isinstance(daily_data, list) and len(daily_data) > 0:
                    # Combine: daily data for older period, hourly for recent (last 24h)
                    # Strategy: Keep all daily candles, then add hourly candles that are newer than the last daily candle
                    if daily_data and hourly_data:
                        # Get the timestamp of the last daily candle
                        last_daily_ts = max([d[0] for d in daily_data])
                        
                        # Keep hourly candles that are newer than the last daily candle
                        # This ensures we get the most recent hourly data
                        recent_hourly = [h for h in hourly_data if h[0] > last_daily_ts]
                        
                        # Combine: all daily + recent hourly (sorted by timestamp)
                        combined = daily_data + recent_hourly
                        # Sort by timestamp to ensure chronological order
                        combined.sort(key=lambda x: x[0])
                        return combined
                    elif hourly_data:
                        # If no daily data, just use hourly
                        return hourly_data
                    else:
                        # Fallback to daily
                        return daily_data
                else:
                    # No daily data, just return hourly
                    return hourly_data
            else:
                # Just return hourly data for 1 day
                return hourly_data
        except Exception as e:
            print(f"REST API OHLC fetch failed: {e}")
        
        return None
    except Exception as e:
        print(f"Error fetching OHLC data: {e}")
        return None


async def generate_chart_image(coin_id: str, coin_name: str = None, days: int = 7, use_candlesticks: bool = True) -> Optional[BytesIO]:
    """Generate a chart image from MCP data. Returns BytesIO of chart image or None.
    Can generate candlestick charts if use_candlesticks=True."""
    try:
        # Import matplotlib
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from datetime import datetime
        
        # Try candlesticks first if requested
        if use_candlesticks:
            ohlc_data = await get_ohlc_data(coin_id, days)
            if ohlc_data and len(ohlc_data) > 0:
                # Convert OHLC data: [timestamp_ms, open, high, low, close]
                timestamps = [datetime.fromtimestamp(candle[0] / 1000) for candle in ohlc_data]
                opens = [candle[1] for candle in ohlc_data]
                highs = [candle[2] for candle in ohlc_data]
                lows = [candle[3] for candle in ohlc_data]
                closes = [candle[4] for candle in ohlc_data]
                
                # Create candlestick chart
                fig, ax = plt.subplots(figsize=(10, 6))
                
                # Draw candlesticks manually using index-based positioning
                num_candles = len(timestamps)
                width = 0.6  # Width of each candle (in index units)
                
                for i, (ts, open_val, high_val, low_val, close_val) in enumerate(zip(timestamps, opens, highs, lows, closes)):
                    # Color: green for up, red for down
                    color = '#26a69a' if close_val >= open_val else '#ef5350'
                    
                    # Draw the wick (high-low line) - use index for x position
                    ax.plot([i, i], [low_val, high_val], color='black', linewidth=1.5, alpha=0.9, zorder=1)
                    
                    # Draw the body (open-close rectangle)
                    body_low = min(open_val, close_val)
                    body_high = max(open_val, close_val)
                    body_height = body_high - body_low
                    
                    # Ensure minimum body height for visibility
                    if body_height < 0.0001:
                        body_height = 0.0001
                        body_low = close_val - 0.00005
                    
                    # Use rectangle for body - position by index
                    rect = plt.Rectangle((i - width/2, body_low), width, body_height, 
                                         facecolor=color, edgecolor='black', linewidth=1, zorder=2)
                    ax.add_patch(rect)
                
                # Formatting
                ax.set_title(f"{coin_name or coin_id.upper()} Price Chart - Candlesticks ({days}d)", 
                           fontsize=14, fontweight='bold')
                ax.set_xlabel('Date', fontsize=10)
                ax.set_ylabel('Price (USD)', fontsize=10)
                ax.grid(True, alpha=0.3, linestyle='--')
                
                # Set x-axis to show dates at candle positions
                ax.set_xlim(-0.5, num_candles - 0.5)
                # Set x-axis labels to dates
                if num_candles <= 20:
                    # Show all labels if few candles
                    ax.set_xticks(range(num_candles))
                    ax.set_xticklabels([ts.strftime('%m/%d') for ts in timestamps], rotation=45, ha='right')
                else:
                    # Show every nth label if many candles
                    step = max(1, num_candles // 10)
                    ax.set_xticks(range(0, num_candles, step))
                    ax.set_xticklabels([timestamps[i].strftime('%m/%d') for i in range(0, num_candles, step)], rotation=45, ha='right')
                
                # Format y-axis for small prices
                all_prices = opens + highs + lows + closes
                max_price = max(all_prices)
                if max_price < 1:
                    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.6f}'.rstrip('0').rstrip('.')))
                else:
                    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.2f}'))
                
                plt.tight_layout()
                
                # Save to BytesIO
                img_buffer = BytesIO()
                plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
                img_buffer.seek(0)
                plt.close()
                
                return img_buffer
        
        # Fallback to line chart if candlesticks failed
        chart_data = await get_chart_data(coin_id, days)
        if not chart_data or "prices" not in chart_data:
            return None
        
        # Extract price data
        prices = chart_data.get("prices", [])
        if not prices:
            return None
        
        # Convert timestamps to datetime and extract prices
        timestamps = [datetime.fromtimestamp(ts[0] / 1000) for ts in prices]
        price_values = [p[1] for p in prices]
        
        # Create the line chart
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(timestamps, price_values, linewidth=2, color='#1f77b4')
        ax.fill_between(timestamps, price_values, alpha=0.3, color='#1f77b4')
        
        # Formatting
        ax.set_title(f"{coin_name or coin_id.upper()} Price Chart ({days}d)", fontsize=14, fontweight='bold')
        ax.set_xlabel('Date', fontsize=10)
        ax.set_ylabel('Price (USD)', fontsize=10)
        ax.grid(True, alpha=0.3)
        
        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, days//7)))
        plt.xticks(rotation=45)
        
        # Format y-axis for small prices
        if max(price_values) < 1:
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.6f}'.rstrip('0').rstrip('.')))
        else:
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.2f}'))
        
        plt.tight_layout()
        
        # Save to BytesIO
        img_buffer = BytesIO()
        plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close()
        
        return img_buffer
    except Exception as e:
        print(f"Error generating chart image: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_dexscreener_url(token_address: str, chain: str = "base") -> str:
    """Get DexScreener chart URL for a token."""
    # DexScreener format: https://dexscreener.com/{chain}/{pair_address}
    # For AIPG on Base
    if token_address.lower() == "0xa1c0deCaFE3E9Bf06A5F29B7015CD373a9854608":
        # Main pair address from API
        return "https://dexscreener.com/base/0x584bed2973b14455c08e26f566646092e2c0ed90527013bfcfcd60fa5e4ae6d2"
    # Generic format - would need to query API to get pair address
    return f"https://dexscreener.com/{chain}/{token_address}"


async def get_crypto_context(message: str) -> str:
    """
    Analyze message and fetch relevant crypto data if needed.
    Returns a formatted string with crypto context to add to LLM prompt.
    """
    # STRICT: Only trigger on VERY EXPLICIT price questions
    # We're being super selective to avoid false positives
    import re
    message_lower = message.lower().strip()
    
    # Very explicit price question patterns using regex for flexibility
    # These patterns look for price-related phrases that can have coin names in between
    strict_price_patterns = [
        r"what'?s?\s+the\s+price",  # "what's the price", "whats the price"
        r"what\s+is\s+the\s+price",  # "what is the price"
        r"how\s+much\s+is",          # "how much is"
        r"current\s+price",           # "current price"
        r"price\s+of",                # "price of"
        r"show\s+me\s+(the\s+)?price", # "show me the price" or "show me price"
        r"give\s+me\s+(the\s+)?price", # "give me the price"
        r"tell\s+me\s+(the\s+)?price", # "tell me the price"
        r"what'?s?\s+it\s+worth",     # "what's it worth"
        r"what\s+is\s+it\s+worth"     # "what is it worth"
    ]
    
    # Check if message contains a strict price pattern
    has_strict_price_pattern = any(re.search(pattern, message_lower) for pattern in strict_price_patterns)
    
    # Also check for coin name + "price" directly adjacent (e.g., "aipg price", "btc price")
    # Simple string matching for common patterns
    direct_price_strings = [
        "aipg price", "ai power grid price",
        "btc price", "bitcoin price",
        "eth price", "ethereum price"
    ]
    
    has_direct_price = any(pattern in message_lower for pattern in direct_price_strings)
    
    # ONLY fetch if we have a very explicit price question
    if not (has_strict_price_pattern or has_direct_price):
        return ""
    
    # Try to extract coin names from message
    # First check for known coins
    coin_ids = []
    known_coins = {
        "bitcoin": "bitcoin",
        "btc": "bitcoin",
        "ethereum": "ethereum",
        "eth": "ethereum",
        "aipg": "ai-power-grid",
        "ai power grid": "ai-power-grid"
    }
    
    # Check for known coins first
    for keyword, coin_id in known_coins.items():
        if keyword in message_lower:
            coin_ids.append(coin_id)
    
    # If no known coins found, try to search for the coin name
    # Extract potential coin name from the message
    if not coin_ids:
        # Try to find a coin name after price-related words
        import re
        # Pattern: "price of X" or "X price" where X might be the coin name
        patterns = [
            r"price\s+of\s+([a-z\s]+?)(?:\s|$)",
            r"how\s+much\s+is\s+([a-z\s]+?)(?:\s|$)",
            r"what'?s?\s+the\s+price\s+of\s+([a-z\s]+?)(?:\s|$)",
            r"([a-z\s]+?)\s+price(?:\s|$)",
        ]
        
        potential_coin_name = None
        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                potential_coin_name = match.group(1).strip()
                # Clean up common words
                potential_coin_name = re.sub(r'\b(coin|token|crypto|currency)\b', '', potential_coin_name).strip()
                if potential_coin_name and len(potential_coin_name) > 1:
                    break
        
        # If we found a potential coin name, search for it
        if potential_coin_name:
            search_results = await search_crypto(potential_coin_name)
            if search_results:
                # Use the first result's ID (highest relevance)
                if isinstance(search_results, list) and len(search_results) > 0:
                    first_result = search_results[0]
                    if isinstance(first_result, dict):
                        # CoinGecko search returns 'id' field (e.g., 'ethereum', 'fart-coin')
                        coin_id = first_result.get("id") or first_result.get("coin_id") or first_result.get("api_symbol")
                        if coin_id:
                            coin_ids.append(coin_id)
                    elif isinstance(first_result, str):
                        # Try to parse as JSON if it's a string
                        try:
                            import json
                            parsed = json.loads(first_result)
                            if isinstance(parsed, dict):
                                coin_id = parsed.get("id") or parsed.get("coin_id") or parsed.get("api_symbol")
                                if coin_id:
                                    coin_ids.append(coin_id)
                        except:
                            pass
    
    if not coin_ids:
        return ""
    
    # Fetch prices for detected coins
    crypto_data = []
    for coin_id in coin_ids:
        price_data = await get_crypto_price(coin_id)
        if price_data:
            crypto_data.append(price_data)
    
    if crypto_data:
        # Just provide raw price data, no formatting instructions
        result = "\n".join(crypto_data)
        return result
    
    return ""