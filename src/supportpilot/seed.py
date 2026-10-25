"""Create one explicitly synthetic order for the local demo."""

import argparse
import os

from .store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", default="demo")
    parser.add_argument("--user", default="alice")
    parser.add_argument("--order-id", default="DEMO-1001")
    args = parser.parse_args()
    Store(os.environ.get("DB_PATH", "data/app.db")).seed(args.tenant, args.user, args.order_id)
    print("Synthetic order created:", args.order_id)


if __name__ == "__main__":
    main()
