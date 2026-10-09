import argparse
from dataclasses import asdict
import json
from pathlib import Path
from .discovery import discover
from .matching import screen, apply_review
from .models import Brief, Job
from .store import Store
from .transport import PublicFetcher
from .verification import verify_application


def main(argv=None):
    parser = argparse.ArgumentParser(prog="jobrouter")
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("seeds", nargs="+")
    collect.add_argument("--db", default="jobs.sqlite")
    collect.add_argument("--budget", type=int, default=100)
    collect.add_argument("--sources", type=int, default=40)
    collect.add_argument("--depth", type=int, default=2)
    collect.add_argument("--workers", type=int, default=6)
    collect.add_argument("--trusted-proxy-host", action="append", default=[], help="Exact deployment-approved public host; never populate from scraped content")
    rank = sub.add_parser("rank")
    rank.add_argument("--db", default="jobs.sqlite")
    rank.add_argument("--brief", required=True)
    rank.add_argument("--reviews")
    verify = sub.add_parser("verify")
    verify.add_argument("--db", default="jobs.sqlite")
    verify.add_argument("--ids", nargs="+", required=True, help="Exact stored identities to check")
    verify.add_argument("--budget", type=int, default=30)
    verify.add_argument("--trusted-proxy-host", action="append", default=[])
    args = parser.parse_args(argv)
    store = Store(args.db)
    if args.command == "collect":
        result = discover(args.seeds, PublicFetcher(budget=args.budget, trusted_proxy_hosts=args.trusted_proxy_host), store, args.sources, args.depth, args.workers)
        print(json.dumps({"jobs": len(result.jobs), "sources": result.sources, "errors": result.errors,
                          "requests": result.requests, "stop_reason": result.stop_reason}, indent=2))
    elif args.command == "verify":
        fetcher = PublicFetcher(budget=args.budget, trusted_proxy_hosts=args.trusted_proxy_host)
        results = []
        for data in store.jobs():
            job = Job.from_dict(data)
            if job.identity in args.ids:
                results.append(verify_application(job, fetcher))
                store.job(job)
        store.receipts(fetcher.receipts)
        print(json.dumps({"results": results, "requests": fetcher.used}, indent=2))
    else:
        brief = Brief(**json.loads(Path(args.brief).read_text())).validate()
        reviews = json.loads(Path(args.reviews).read_text()) if args.reviews else {}
        output = []
        for data in store.jobs():
            job = Job.from_dict(data)
            decision = screen(job, brief)
            if job.identity in reviews:
                decision = apply_review(decision, job, reviews[job.identity], brief)
            output.append({"job": data, "decision": decision.to_dict()})
        output.sort(key=lambda x: (x["decision"]["category"] != "qualified", -x["decision"]["score"], x["job"]["title"]))
        print(json.dumps({"brief_digest": brief.digest, "results": output,
                          "qualified_count": sum(x["decision"]["category"] == "qualified" for x in output)}, indent=2))


if __name__ == "__main__":
    main()
