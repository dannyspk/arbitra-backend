from arbitrage.hotcoins import find_hot_coins
import json

if __name__ == '__main__':
    hot = find_hot_coins(max_results=20, exclude_top_by_marketcap=20)
    print(json.dumps(hot, indent=2))
