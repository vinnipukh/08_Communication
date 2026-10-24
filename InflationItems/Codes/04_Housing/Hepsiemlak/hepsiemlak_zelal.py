"""
Zelal's daily Hepsiemlak rental crawl: open this file and press Run (the green button) in the IDE.

Starts the headless scraper in the background for Zelal's provinces (shards.json, key "zelal") and
returns at once; the crawl keeps running after the IDE run ends. Log and progress: checkpoints/.
Output: InflationItems/Datas/04_Housing/Hepsiemlak/YYYY-MM-DD_zelal.csv
"""

from launcher import start

if __name__ == "__main__":
    start("zelal")
