"""kingctl: command line interface of Dopamine King."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from . import __version__, config
from .generate.types import Brief

ROOT = Path(__file__).resolve().parents[2]


# -- small helpers ------------------------------------------------------------------
def _bar(value: float, width: int = 20, top: float = 100.0) -> str:
    filled = max(0, min(width, round(width * value / top)))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _emit(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _store(args: argparse.Namespace):
    from .store import Store
    return Store(args.db or config.db_path())


def _fetcher():
    from .net import HttpFetcher
    return HttpFetcher(config.user_agent(), cache_dir=config.cache_dir())


def _polite(store=None):
    from .ingest.polite import PoliteFetcher
    from .ingest.robots import RobotsPolicy
    inner = _fetcher()
    robots = RobotsPolicy(inner, config.user_agent())
    return PoliteFetcher(inner, robots, store), robots


def _vertical(args: argparse.Namespace):
    """The vertical asked for with --vertical (or the one a brief names), else None."""
    name = getattr(args, "vertical", None)
    if not name or name == "general":
        return None
    from .verticals import VerticalError, load_vertical
    try:
        return load_vertical(name)
    except VerticalError as err:
        raise SystemExit(f"error: {err}")


def _registry(args: argparse.Namespace):
    from .ingest.registry import load_registry
    explicit = getattr(args, "registry", None)
    vertical = _vertical(args)
    if vertical is not None and not explicit:
        return vertical.brands()
    override = explicit or (config.home_dir() / "sources.json")
    path = Path(override)
    return load_registry(path if path.exists() else None)


def _load_brief(args: argparse.Namespace) -> Brief:
    vertical = _vertical(args)
    if getattr(args, "sample", None):
        if vertical is None:
            raise SystemExit("error: --sample needs --vertical (for example --vertical pbm --sample mito-light-cs)")
        samples = vertical.briefs()
        if args.sample not in samples:
            raise SystemExit(f"error: no sample {args.sample!r}; available: {', '.join(samples)}")
        return samples[args.sample]
    if getattr(args, "brief", None):
        brief = Brief.from_dict(json.loads(Path(args.brief).read_text("utf-8")))
    else:
        missing = [f for f in ("brand", "topic", "audience") if not getattr(args, f, None)]
        if missing:
            raise SystemExit(f"error: provide --brief FILE or all of --brand --topic --audience (missing: {', '.join(missing)})")
        brief = Brief(
            brand=args.brand, topic=args.topic, audience=args.audience, goal=args.goal, lang=args.lang, tone=args.tone,
            keyword=args.keyword, offer=args.offer, cta=args.cta, facts=args.fact or [], avoid=args.avoid or [],
            cohort=args.cohort, sponsored=args.sponsored,
        )
    if vertical is not None:
        brief.vertical = vertical.id
        if getattr(args, "claims_profile", None):
            brief.claims_profile = args.claims_profile
        elif brief.claims_profile == "general":
            brief.claims_profile = vertical.claims_profile
    elif getattr(args, "claims_profile", None):
        brief.claims_profile = args.claims_profile
    if getattr(args, "safety_note", None):
        brief.safety_note = args.safety_note
    return brief


def _brief_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--brief", help="JSON file with a Brief")
    p.add_argument("--brand"), p.add_argument("--topic"), p.add_argument("--audience")
    p.add_argument("--goal", default="awareness", choices=["awareness", "consideration", "conversion", "retention", "community"])
    p.add_argument("--lang", default="en", choices=["en", "cs"])
    p.add_argument("--tone", default="friendly, direct, no hype")
    p.add_argument("--keyword"), p.add_argument("--offer"), p.add_argument("--cta"), p.add_argument("--cohort")
    p.add_argument("--fact", action="append", help="first-party fact, repeatable")
    p.add_argument("--avoid", action="append", help="term to avoid, repeatable")
    p.add_argument("--sponsored", action="store_true")
    p.add_argument("--vertical", help="industry profile, for example pbm (photobiomodulation); 'general' for none")
    p.add_argument("--sample", help="start from a sample brief of the vertical, for example mito-light-cs")
    p.add_argument("--claims-profile", choices=["general", "wellness"], help="wellness: non-medical device, no disease or treatment claims")
    p.add_argument("--safety-note", help="the manufacturer's own safety text for long-form content")


def _synthetic_analyses(vertical: Any = None):
    from .analysis import analyze_items
    from .synth import generate_corpus
    brands, items = generate_corpus(config=vertical.synth() if vertical is not None else None)
    cohort = {b.id: b.cohort for b in brands}
    return items, cohort, analyze_items(items, cohort)


def _analyses_from_store(store, synthetic: bool | None):
    from .analysis import analyze_items
    items = list(store.iter_items(synthetic=synthetic))
    cohort = {b.id: b.cohort for b in store.list_brands()}
    return items, cohort, analyze_items(items, cohort)


# -- commands -----------------------------------------------------------------------
def cmd_score(args: argparse.Namespace) -> int:
    from .scoring import score_hook
    body = Path(args.body).read_text("utf-8") if args.body else ""
    res = score_hook(args.text, body, lang=args.lang)
    if args.json:
        _emit(res.to_dict())
        return 0
    cs = res.lang == "cs"
    print(f"Dopamine Score {res.total:5.1f} / 100   clickbait risk {res.clickbait_risk:.0%}   lang {res.lang}")
    for k, v in res.parts.items():
        print(f"  {k:<10} {_bar(v)} {v:5.1f}")
    for tip in res.tips:
        print(f"  tip: {tip['cs' if cs else 'en']}")
    if res.spans:
        print("  matched: " + ", ".join(f'{s.category}="{s.text}"' for s in res.spans))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    from .analysis import compare_hooks
    c = compare_hooks(args.a, args.b, lang=args.lang)
    if args.json:
        _emit(c.to_dict())
        return 0
    print(f"A {c.a.total:5.1f}  vs  B {c.b.total:5.1f}   P(A wins) = {c.p_a_wins:.0%}   winner: {c.winner.upper()}")
    for r in (c.reasons_cs if c.a.lang == "cs" else c.reasons_en):
        print(f"  - {r}")
    return 0


def cmd_synth(args: argparse.Namespace) -> int:
    from .synth import populate_store
    with _store(args) as store:
        b, i = populate_store(store, seed=args.seed)
    print(f"Synthetic corpus written: {b} fictional brands, {i} items (all flagged synthetic).")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    from .analysis import Benchmark, calibrate_weights, mine_patterns
    if args.demo:
        items, cohort, analyses = _synthetic_analyses()
        origin = "synthetic demo corpus"
    else:
        with _store(args) as store:
            items, cohort, analyses = _analyses_from_store(store, False if args.real_only else None)
        origin = "database"
        if not items:
            print("The database has no items. Use `kingctl scrape`, `kingctl import-csv`, or add --demo.", file=sys.stderr)
            return 1
    titles = {i.id: i.title for i in items}
    bench = Benchmark(analyses)
    patterns = mine_patterns(analyses, titles, cohort=args.cohort, n_boot=args.boot)
    cal = calibrate_weights(analyses)
    if args.save_calibration:
        cal.save(args.save_calibration)
    if args.json:
        _emit({"origin": origin, "n_items": len(items), "cohorts": {c: bench.stats(c) for c in bench.cohorts()},
               "patterns": [p.to_dict() for p in patterns], "calibration": cal.to_dict()})
        return 0
    print(f"Analysed {len(items)} items from the {origin}.")
    print("\nScore distribution per cohort (Dopamine Score):")
    for c in bench.cohorts():
        st = bench.stats(c)
        print(f"  {c:<22} n={int(st['n']):4d}  p25 {st['p25']:5.1f}  median {st['p50']:5.1f}  p90 {st['p90']:5.1f}")
    print("\nWhat goes with success (index points per +1 SD, 95% bootstrap interval):")
    for p in patterns[:10]:
        flag = "*" if p.significant else " "
        print(f" {flag} {p.label_en:<34} {p.adj_effect:+6.2f}  [{p.adj_ci[0]:+6.2f}, {p.adj_ci[1]:+6.2f}]")
    print("\nCalibration: " + (f"weights {', '.join(f'{k} {v:.2f}' for k, v in cal.weights.items())}; "
                               f"out-of-fold rank correlation {cal.cv_spearman_default:.2f} -> {cal.cv_spearman_calibrated:.2f}"))
    for n in cal.notes:
        print("  note: " + n)
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    from .analysis import Benchmark
    if args.demo:
        items, cohort, analyses = _synthetic_analyses()
    else:
        with _store(args) as store:
            items, cohort, analyses = _analyses_from_store(store, None)
        if not items:
            items, cohort, analyses = _synthetic_analyses()
            print("(database is empty: using the synthetic demo corpus)", file=sys.stderr)
    res = Benchmark(analyses).compare(args.text, cohort=args.cohort, lang=args.lang)
    if args.json:
        _emit(res)
        return 0
    print(f"Score {res['score']:.1f}  |  percentile {res['percentile']:.0f} in {args.cohort or 'all'}  |  vs median {res['vs_median']:+.1f}, vs p90 {res['vs_p90']:+.1f}")
    for g in res["feature_gaps"]:
        print(f"  top performers vs you: {g['feature']:<20} top {g['top']:.2f}  yours {g['yours']:.2f}")
    return 0


def cmd_lab(args: argparse.Namespace) -> int:
    from . import lab
    if args.lab_cmd == "ab":
        (ca, na), (cb, nb) = (tuple(int(x) for x in s.split("/")) for s in (args.a, args.b))
        f, b = lab.two_proportion_test(ca, na, cb, nb), lab.bayes_ab(ca, na, cb, nb)
        if args.json:
            _emit({"frequentist": f.to_dict(), "bayesian": b.to_dict()})
            return 0
        print(f"A {f.rate_a:.2%} ({ca}/{na})   B {f.rate_b:.2%} ({cb}/{nb})   uplift {f.rel_uplift:+.1%}" if f.rel_uplift is not None else "")
        print(f"z = {f.z:.3f}   p = {f.p_value:.4f}   95% interval for B - A: [{f.ci_diff[0]:+.4f}, {f.ci_diff[1]:+.4f}]   significant: {f.significant}")
        print(f"Bayesian: P(B better) = {b.p_b_better:.1%}   expected loss if you ship B = {b.expected_loss_choose_b:.5f}")
    elif args.lab_cmd == "size":
        n = lab.sample_size_per_arm(args.baseline, args.mde, args.alpha, args.power)
        print(f"{n} visitors per arm to detect a {args.mde:.0%} relative lift on a {args.baseline:.1%} baseline (alpha {args.alpha}, power {args.power}).")
    elif args.lab_cmd == "bandit":
        rates = [float(x) for x in args.rates.split(",")]
        res = lab.compare_policies(rates, args.rounds, seeds=args.seeds)
        if args.json:
            _emit(res)
            return 0
        print(f"True rates {rates}, {args.rounds} rounds, mean over {args.seeds} runs:")
        for name, r in res.items():
            print(f"  {name:<9} regret {r['mean_regret']:8.2f}   best-arm share {r['mean_best_arm_share']:.0%}   conversions {r['mean_conversions']:.0f}")
    elif args.lab_cmd == "peek":
        fp = lab.peeking_false_positive_rate(args.looks, trials=args.trials)
        print(f"Checking an A/A test {args.looks} times and stopping at the first p < 0.05 gives {fp:.0%} false positives (nominal 5%).")
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    from .ingest.registry import apply_verification, save_registry, verify_all
    brands = _registry(args)
    if args.cohort:
        brands = [b for b in brands if b.cohort == args.cohort]
    if args.brand:
        brands = [b for b in brands if b.id in args.brand]
    if args.src_cmd == "list":
        for b in brands:
            print(f"{b.id:<22} {b.cohort:<22} {b.country or '--':<3} {b.homepage or ''}{'' if not b.verified else '  [verified]'}")
        print(f"\n{len(brands)} brands. Endpoints are hints until `kingctl sources verify` confirmed them.")
        return 0
    brands = brands[: args.limit] if args.limit else brands
    polite, robots = _polite()
    updated, ok = [], 0
    for report in verify_all(brands, polite, robots, progress=lambda m: print("  " + m, file=sys.stderr)):
        brand = next(b for b in brands if b.id == report.brand_id)
        new = apply_verification(brand, report)
        updated.append(new)
        ok += new.verified
        print(f"{report.brand_id:<22} homepage {'ok' if report.homepage_ok else 'FAIL':<4} robots {'ok' if report.robots_ok else 'FAIL':<4} "
              f"feeds {len(report.feeds)} sitemaps {len(report.sitemaps)}  {'; '.join(report.errors[:1])}")
    print(f"\n{ok}/{len(updated)} brands verified.")
    if args.save and updated:
        by_id = {b.id: b for b in _registry(args)}
        by_id.update({b.id: b for b in updated})
        save_registry(list(by_id.values()), args.save)
        print(f"Registry written to {args.save}")
    return 0


def cmd_scrape(args: argparse.Namespace) -> int:
    from .ingest.pipeline import Scraper
    from .ingest.registry import seed_store
    brands = [b for b in _registry(args) if (not args.brand or b.id in args.brand) and (not args.cohort or b.cohort == args.cohort)]
    if args.only_verified:
        brands = [b for b in brands if b.verified]
    brands = brands[: args.limit] if args.limit else brands
    with _store(args) as store:
        seed_store(store, brands)
        polite, _ = _polite(store)
        scraper = Scraper(store, polite, max_items_per_brand=args.per_brand, since_days=args.since_days,
                          fetch_pages=args.fetch_pages, progress=lambda m: print("  " + m, file=sys.stderr))
        total_new = 0
        for rep in scraper.scrape_all(brands):
            total_new += rep.new
            print(f"{rep.brand_id:<22} candidates {rep.candidates:4d}  new {rep.new:4d}  blocked {rep.blocked}  errors {len(rep.errors)}")
            for line in rep.errors[:2] + rep.blocked_reasons[:2]:
                print(f"    {line[:160]}")
        print(f"\n{total_new} new items stored in {store.path}. Next: kingctl enrich, kingctl analyze")
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    from .ingest.signals import enrich_signals
    with _store(args) as store:
        n = enrich_signals(store, _fetcher(), limit=args.limit)
    print(f"Added public popularity signals to {n} items.")
    return 0


def cmd_import_csv(args: argparse.Namespace) -> int:
    from .ingest.signals import import_analytics_csv
    with _store(args) as store:
        n = import_analytics_csv(store, args.file, args.brand_id, platform=args.platform, format=args.format)
    print(f"Imported {n} rows of first-party analytics for {args.brand_id}.")
    return 0


def _ledger(path: str | None, vertical: Any = None):
    from .research.ledger import Ledger
    if vertical is not None and path is None:
        return vertical.ledger()
    return Ledger.load(path)


def cmd_evidence(args: argparse.Namespace) -> int:
    if args.ev_cmd == "search":
        from .research.search import search_studies
        studies, errors = search_studies(args.query, _fetcher(), sources=tuple(args.sources.split(",")), limit=args.limit,
                                         mailto=args.mailto)
        if args.json:
            _emit({"studies": [s.to_dict() for s in studies], "errors": errors})
            return 0
        for s in studies:
            print(f"[{s.grade}] {s.year or '----'} {s.design:<18} {s.title[:90]}  ({s.doi or s.url or s.id})")
        for e in errors:
            print("  source error: " + e, file=sys.stderr)
        return 0 if studies or not errors else 2
    vertical = _vertical(args)
    ledger = _ledger(args.ledger, vertical)
    if args.ev_cmd == "claims":
        if vertical is None:
            raise SystemExit("error: the claims map belongs to a vertical, for example: kingctl evidence claims --vertical pbm")
        for row in vertical.claim_map(ledger):
            note = f"  ({row['n_pending']} pending verification)" if row["n_pending"] else ""
            print(f"{row['id']:<26} {row['class']:<9} {row['label']:<10} studies {row['n_studies']}{note}  {row['name_en']}")
        print("\nThe label counts verified studies only and never exceeds the curated cap of the topic.")
        return 0
    if args.ev_cmd == "ledger":
        ids = [args.tactic] if args.tactic else list(ledger.tactics)
        for tid in ids:
            s = ledger.summary(tid)
            print(f"{tid:<32} {s.label:<10} grade {s.grade or '-'}  studies {s.n_studies}  {s.headline_en}")
            if args.tactic:
                for study, link in ledger.evidence_for(tid):
                    print(f"    [{study.grade}] {link.direction:<11} {study.year} {study.title[:80]}\n        {link.note_en}")
        return 0
    if args.ev_cmd == "verify":
        results = ledger.verify(_fetcher(), mailto=args.mailto)
        for r in results:
            print(f"{r['status']:<11} {r['study_id']}  {r['detail']}")
        if args.save:
            ledger.save(args.save)
            print(f"Ledger written to {args.save}")
        return 0
    return 1


def cmd_formats(args: argparse.Namespace) -> int:
    from .generate import formats as registry
    for s in registry.list_formats(args.family):
        print(f"{s.id:<24} {s.family:<8} {s.platform:<10} {s.name_en}")
    return 0


def cmd_forge(args: argparse.Namespace) -> int:
    from .generate.packs import DEFAULT_FORMATS, build_pack, slot_template
    from .generate.providers import FileWriter, WriterError, WriterRefused, select_writer
    from .generate import formats as registry
    brief = _load_brief(args)
    formats = list(registry.all_formats()) if args.formats == "all" else (args.formats.split(",") if args.formats else list(DEFAULT_FORMATS))
    ledger = _ledger(None, _vertical(argparse.Namespace(vertical=brief.vertical)))
    if args.emit_slots:
        template = slot_template(brief, formats, ledger=ledger)
        Path(args.emit_slots).write_text(json.dumps(template, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"Wrote the slots of {len(template) - 1} formats to {args.emit_slots}. Fill the text fields (yourself or with any model), then run "
              f"forge with --writer file --fills {args.emit_slots}")
        return 0
    try:
        if args.writer == "file":
            if not args.fills:
                raise SystemExit("error: --writer file needs --fills PATH (write a template with --emit-slots PATH)")
            writer = FileWriter(args.fills)
        else:
            writer = select_writer(args.writer, tier=args.tier) if args.writer != "offline" else select_writer("offline")
    except ValueError as err:
        raise SystemExit(f"error: {err}")
    except WriterError as err:
        raise SystemExit(f"error: {err}")
    t0 = time.perf_counter()
    try:
        pack = build_pack(brief, formats, writer=writer, ledger=ledger, improve_rounds=args.improve)
    except WriterRefused as err:
        print(f"The model declined this brief: {err}", file=sys.stderr)
        return 3
    except WriterError as err:
        print(f"Writer error: {err}", file=sys.stderr)
        return 3
    if args.out:
        written = pack.save(args.out)
        print(f"Wrote {len(written)} files to {args.out}")
    if args.json:
        _emit(pack.to_dict())
    elif not args.quiet:
        print(pack.to_markdown(brief.lang))
    s = pack.summary
    print(f"\n[{pack.writer}] {s['n_items']} formats in {time.perf_counter() - t0:.1f}s | verdicts {s['verdicts']} | "
          f"{s['errors']} errors, {s['warnings']} warnings, {s['open_slots']} open slots", file=sys.stderr)
    usage = getattr(writer, "usage", None)
    if usage and usage.calls:
        print(f"[tokens] calls {usage.calls}, input {usage.input_tokens}, output {usage.output_tokens}", file=sys.stderr)
    if isinstance(writer, FileWriter):
        print(f"[file] {len(writer.used)} slots filled from {args.fills}", file=sys.stderr)
        for where, problems in sorted(writer.violations.items()):
            print(f"[file] {where} breaks its limits: {'; '.join(problems)}", file=sys.stderr)
    return 0


def cmd_guru(args: argparse.Namespace) -> int:
    from .guru import build_plan
    brief = _load_brief(args)
    plan = build_plan(brief, weeks=args.weeks, posts_per_week=args.posts_per_week,
                      channels=args.channels.split(",") if args.channels else None)
    if args.json:
        _emit(plan.to_dict())
    else:
        print(plan.to_markdown(brief.lang))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Run the claims profile over existing copy (a product page, an article, a post) and list what a regulator would read."""
    from .generate.guard import TrustShield
    from .scoring import detect_lang
    vertical = _vertical(args)
    if vertical is None:
        from .verticals import load_vertical
        vertical = load_vertical("pbm")
    texts: list[tuple[str, str]] = []
    for name in args.files:
        if name == "-":
            texts.append(("stdin", sys.stdin.read()))
        else:
            path = Path(name)
            if not path.exists():
                raise SystemExit(f"error: no such file: {name}")
            texts.append((name, path.read_text("utf-8")))
    shield = TrustShield(vertical.ledger())
    rows: list[dict[str, Any]] = []
    worst = 0
    for name, text in texts:
        lang = args.lang or detect_lang(text)
        brief = Brief(brand=args.brand or vertical.default_brand or "brand", topic="audit", audience="audit", lang=lang,
                      vertical=vertical.id, claims_profile=args.claims_profile or vertical.claims_profile, facts=args.fact or [])
        issues = [i for i in shield.check(text, brief) if i.code != "AI_DISCLOSURE_REMINDER"]
        errors = sum(i.severity == "error" for i in issues)
        worst = max(worst, 1 if errors else 0)
        rows.append({"file": name, "lang": lang, "errors": errors, "warnings": sum(i.severity == "warn" for i in issues),
                     "issues": [i.to_dict() for i in issues]})
        if not args.json:
            print(f"== {name} ({lang}): {errors} errors, {rows[-1]['warnings']} warnings, verdict {shield.verdict(issues)}")
            for i in issues:
                print(f"  [{i.severity:<5}] {i.code:<20} {i.where or ''}\n      {i.message}")
    if args.json:
        _emit(rows)
    return worst


def cmd_visibility(args: argparse.Namespace) -> int:
    from .generate.visibility import AnswerRecord, analyze_answers
    raw = json.loads(Path(args.answers).read_text("utf-8"))
    records = [AnswerRecord(r["query"], r.get("engine", "unknown"), r["text"], r.get("cited_urls", [])) for r in raw]
    rep = analyze_answers(records, args.brand, args.competitors.split(",") if args.competitors else [],
                          brand_domains=args.domains.split(",") if args.domains else None, lang=args.lang)
    if args.json:
        _emit(rep.__dict__)
        return 0
    print(f"{rep.brand}: mentioned in {rep.mention_rate:.0%} of {rep.n_answers} answers, cited in {rep.citation_rate:.0%}, sentiment {rep.sentiment:+.2f}")
    for name, share in rep.share_of_voice.items():
        print(f"  share of voice {name:<20} {share:.0%}")
    for gap in rep.gaps:
        print(f"  gap: {gap}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve
    page = Path(args.page) if args.page else ROOT / "web" / "dist" / "dopamine-king.html"
    ledger = None
    try:
        ledger = _ledger(None)
    except Exception:
        pass
    serve(args.host, args.port, writer=args.writer, page_path=page, allow_remote=args.allow_remote, ledger=ledger, verbose=args.verbose)
    return 0


def cmd_build_web(args: argparse.Namespace) -> int:
    import importlib.util
    script = ROOT / "scripts" / "build_web.py"
    if not script.exists():
        print("scripts/build_web.py not found (run from a source checkout).", file=sys.stderr)
        return 1
    spec = importlib.util.spec_from_file_location("build_web", script)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return int(module.main(["--out", args.out, "--vertical", args.vertical]
                           + (["--bundle", args.bundle] if args.bundle else [])) or 0)


def cmd_demo(args: argparse.Namespace) -> int:
    """End to end tour on the synthetic corpus: no network, no API key."""
    from .analysis import Benchmark, calibrate_weights, compare_hooks, mine_patterns
    from .lab import compare_policies, two_proportion_test, bayes_ab
    from .scoring import score_hook

    def head(text: str) -> None:
        print(f"\n=== {text} " + "=" * max(0, 70 - len(text)))

    t0 = time.perf_counter()
    vertical = _vertical(args)
    edition = f" | {vertical.meta.get('edition_en', vertical.name('en'))}" if vertical is not None else ""
    print(f"DOPAMINE KING {__version__}  demo (synthetic data, offline){edition}")
    head("1. Corpus: fictional brands with planted effects")
    items, cohort, analyses = _synthetic_analyses(vertical)
    print(f"{len(items)} items, {len(set(cohort.values()))} cohorts, Success Index computed from engagement RATES per cohort and platform")
    bench = Benchmark(analyses)

    head("2. Pattern mining: what goes with success")
    titles = {i.id: i.title for i in items}
    for p in mine_patterns(analyses, titles, n_boot=60)[:6]:
        print(f"  {'*' if p.significant else ' '} {p.label_en:<30} {p.adj_effect:+6.2f}  [{p.adj_ci[0]:+6.2f}, {p.adj_ci[1]:+6.2f}]")
    cal = calibrate_weights(analyses)
    print(f"  calibration: out-of-fold rank correlation {cal.cv_spearman_default:.2f} -> {cal.cv_spearman_calibrated:.2f}")

    head("3. Score and benchmark hooks")
    if vertical is not None:
        hooks = ("5 mistakes people make when choosing a red light panel", "Our Q3 update on light panels",
                 "You won't BELIEVE this one trick!!!", "5 chyb při výběru červeného světla")
        local = "pbm-cz-sk"
    else:
        hooks = ("7 mistakes every beginner runner makes (and how to fix them)", "Our Q3 company update",
                 "You won't BELIEVE this one trick!!!", "7 chyb, které dělá každý začátečník v běhu")
        local = "cz-local"
    for text in hooks:
        r = score_hook(text)
        pct = bench.percentile(r.total, local if r.lang == "cs" else None)
        print(f"  {r.total:5.1f} {_bar(r.total, 12)} p{pct:3.0f}  risk {r.clickbait_risk:4.0%}  {text}")
    if vertical is not None:
        c = compare_hooks("How to choose a red light panel without reading a spec sheet", "A new panel release")
    else:
        c = compare_hooks("Why most marketing dashboards lie to you", "A new dashboard release")
    print(f"  duel: P(A wins) {c.p_a_wins:.0%}  " + "; ".join(c.reasons_en[:1]))
    if vertical is not None:
        from .generate import claims as claims_mod
        profile = claims_mod.load_profile(vertical.id, vertical.claims_profile)
        print("  claims check (non-medical wellness profile):")
        for text in ("Red light cures joint pain.", "Some studies suggest red light may support recovery after exercise.",
                     "Za 4 týdny uvidíte méně vrásek.", "Panel není zdravotnický prostředek."):
            found = sorted({h.code for h in profile.scan_text(text)})
            print(f"    {'BLOCKED' if {'CLAIM_MEDICAL', 'CLAIM_AVOID', 'DISEASE_MENTION', 'STATUS_CLAIM', 'SAFETY_ABSOLUTE'} & set(found) else 'ok     ' if not found else 'review '}  "
                  f"{text}  {', '.join(found)}")

    head("4. Lab: honest experimentation")
    f = two_proportion_test(100, 1000, 130, 1000)
    b = bayes_ab(100, 1000, 130, 1000)
    print(f"  A/B 10.0% vs 13.0%: z {f.z:.2f}, p {f.p_value:.3f}, P(B better) {b.p_b_better:.0%}")
    res = compare_policies([0.03, 0.05, 0.04, 0.06], 4000, ("uniform", "thompson"), seeds=6)
    print(f"  bandit regret: even split {res['uniform']['mean_regret']:.0f} vs Thompson {res['thompson']['mean_regret']:.0f}")

    head("5. Evidence ledger")
    try:
        ledger = _ledger(None, vertical)
        if vertical is not None:
            for row in vertical.claim_map(ledger):
                if row["id"] in ("pbm-exercise-performance", "pbm-muscle-recovery", "pbm-skin-appearance", "pbm-pain-joints"):
                    print(f"  {row['id']:<26} {row['class']:<9} {row['label']:<10} verified studies {row['n_studies']}, pending {row['n_pending']}")
        else:
            for tid in ("dopamine-myth", "geo-cite-sources", "ab-testing-peeking"):
                s = ledger.summary(tid)
                print(f"  {tid:<22} {s.label:<10} {s.headline_en}")
        st = ledger.stats()
        print(f"  {len(ledger.studies)} studies in the ledger, {st.get('verified', 0)} verified (the rest wait for `kingctl evidence verify`): {st.get('by_grade', {})}")
    except Exception as err:
        print(f"  (research module not available: {err})")

    head("6. Forge: a content pack from one brief (offline writer)")
    try:
        from .generate.packs import build_pack
        if vertical is not None:
            brief = vertical.briefs(ledger)["mito-light-en"]
            formats = ["hook_set", "instagram_caption", "short_video_script", "seo_article", "geo_answer_page"]
        else:
            brief = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", cohort="sport", keyword="running shoes for beginners",
                          facts=["Our Aero 2 weighs 210 g."], cta="Try the Aero 2 for 30 days")
            formats = ["hook_set", "linkedin_post", "short_video_script", "seo_article", "geo_answer_page"]
        pack = build_pack(brief, formats, ledger=ledger if "ledger" in dir() else None)
        for item in pack.items:
            print(f"  {item.format:<20} hook {item.scores['dopamine']:5.1f}  {item.verdict:<8} open slots {len(item.slots_open):2d}  {item.hook[:46]}")
        print("  The offline writer never invents prose: open slots show [[ADD: ...]]. Use --writer anthropic for Claude.")
    except Exception as err:
        print(f"  (generators not available: {type(err).__name__}: {err})")

    head("7. Guru: 4 week plan")
    try:
        from .guru import build_plan
        plan = build_plan(vertical.briefs()["mito-light-en"] if vertical is not None else
                          Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", cohort="sport", facts=["Our Aero 2 weighs 210 g."]))
        print(f"  channels: {', '.join(c['id'] for c in plan.channels)}; {len(plan.calendar)} calendar slots; {len(plan.experiments)} experiments")
        print(f"  first slot: week {plan.calendar[0]['week']} {plan.calendar[0]['day']} {plan.calendar[0]['channel']} -> {plan.calendar[0]['hook']}")
    except Exception as err:
        print(f"  (planner not available: {err})")

    print(f"\nDone in {time.perf_counter() - t0:.1f}s. Next: kingctl build-web && kingctl serve   (the game)  |  kingctl forge --help")
    return 0


# -- parser -------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kingctl", description="Dopamine King: evidence-driven content intelligence, wrapped in a game.")
    p.add_argument("--version", action="version", version=f"kingctl {__version__}")
    p.add_argument("--db", help="SQLite database (default: $KING_DB or .king/king.sqlite)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("demo", help="end to end tour on synthetic data (offline)")
    s.add_argument("--vertical", help="tour of an edition, for example pbm (MITO LIGHT)")
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("score", help="Dopamine Score of a hook")
    s.add_argument("text"), s.add_argument("--body"), s.add_argument("--lang", choices=["en", "cs"]), s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_score)

    s = sub.add_parser("compare", help="head to head duel of two hooks")
    s.add_argument("a"), s.add_argument("b"), s.add_argument("--lang", choices=["en", "cs"]), s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_compare)

    s = sub.add_parser("synth", help="write the synthetic demo corpus into the database")
    s.add_argument("--seed", type=int, default=7)
    s.set_defaults(fn=cmd_synth)

    s = sub.add_parser("analyze", help="benchmarks, patterns and calibration of the corpus")
    s.add_argument("--demo", action="store_true", help="use the synthetic corpus"), s.add_argument("--real-only", action="store_true")
    s.add_argument("--cohort"), s.add_argument("--boot", type=int, default=100), s.add_argument("--save-calibration")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("benchmark", help="percentile of a hook against the corpus")
    s.add_argument("text"), s.add_argument("--cohort"), s.add_argument("--lang", choices=["en", "cs"])
    s.add_argument("--demo", action="store_true"), s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_benchmark)

    s = sub.add_parser("lab", help="A/B statistics, sample sizes, bandits, peeking")
    ls = s.add_subparsers(dest="lab_cmd", required=True)
    x = ls.add_parser("ab"); x.add_argument("--a", required=True, help="conversions/visitors, e.g. 100/1000"); x.add_argument("--b", required=True); x.add_argument("--json", action="store_true")
    x = ls.add_parser("size"); x.add_argument("--baseline", type=float, required=True); x.add_argument("--mde", type=float, default=0.2); x.add_argument("--alpha", type=float, default=0.05); x.add_argument("--power", type=float, default=0.8)
    x = ls.add_parser("bandit"); x.add_argument("--rates", required=True); x.add_argument("--rounds", type=int, default=5000); x.add_argument("--seeds", type=int, default=10); x.add_argument("--json", action="store_true")
    x = ls.add_parser("peek"); x.add_argument("--looks", type=int, default=10); x.add_argument("--trials", type=int, default=1000)
    s.set_defaults(fn=cmd_lab)

    s = sub.add_parser("sources", help="brand registry: list or verify endpoints (network)")
    ss = s.add_subparsers(dest="src_cmd", required=True)
    for name in ("list", "verify"):
        x = ss.add_parser(name)
        x.add_argument("--cohort"), x.add_argument("--brand", action="append"), x.add_argument("--registry")
        x.add_argument("--vertical", help="use the brand registry of a vertical, for example pbm")
        if name == "verify":
            x.add_argument("--limit", type=int), x.add_argument("--save", help="write the verified registry to this JSON file")
    s.set_defaults(fn=cmd_sources)

    s = sub.add_parser("scrape", help="polite collection of public brand content (network)")
    s.add_argument("--brand", action="append"), s.add_argument("--cohort"), s.add_argument("--registry"), s.add_argument("--limit", type=int)
    s.add_argument("--per-brand", type=int, default=50), s.add_argument("--since-days", type=int, default=365)
    s.add_argument("--fetch-pages", action="store_true"), s.add_argument("--only-verified", action="store_true")
    s.add_argument("--vertical", help="scrape the brand registry of a vertical, for example pbm")
    s.set_defaults(fn=cmd_scrape)

    s = sub.add_parser("enrich", help="add public popularity signals (Hacker News) to scraped items (network)")
    s.add_argument("--limit", type=int, default=100)
    s.set_defaults(fn=cmd_enrich)

    s = sub.add_parser("import-csv", help="import first-party analytics (CSV) as ground truth")
    s.add_argument("file"), s.add_argument("brand_id"), s.add_argument("--platform", default="blog"), s.add_argument("--format", default="post")
    s.set_defaults(fn=cmd_import_csv)

    s = sub.add_parser("evidence", help="studies: search, ledger, verify (search and verify need network)")
    es = s.add_subparsers(dest="ev_cmd", required=True)
    x = es.add_parser("search"); x.add_argument("query"); x.add_argument("--sources", default="openalex,crossref,arxiv,pubmed"); x.add_argument("--limit", type=int, default=10); x.add_argument("--mailto", default=None); x.add_argument("--json", action="store_true")
    x = es.add_parser("ledger"); x.add_argument("--tactic"); x.add_argument("--ledger"); x.add_argument("--vertical")
    x = es.add_parser("claims"); x.add_argument("--ledger"); x.add_argument("--vertical")
    x = es.add_parser("verify"); x.add_argument("--ledger"); x.add_argument("--mailto", default=None); x.add_argument("--save"); x.add_argument("--vertical")
    s.set_defaults(fn=cmd_evidence)

    s = sub.add_parser("formats", help="list content formats")
    s.add_argument("--family")
    s.set_defaults(fn=cmd_formats)

    s = sub.add_parser("forge", help="generate a content pack (articles, posts, video scripts, ads) from one brief")
    _brief_flags(s)
    s.add_argument("--formats", help="comma separated ids, or 'all' (default: a balanced set)")
    s.add_argument("--writer", default="auto", choices=["auto", "offline", "file", "anthropic"],
                   help="offline (structure only), file (texts from --fills), anthropic (Claude) or auto")
    s.add_argument("--fills", help="JSON file with the slot texts for --writer file (write a template with --emit-slots)")
    s.add_argument("--emit-slots", help="write every slot of the chosen formats, with instructions and limits, to this JSON file and stop")
    s.add_argument("--tier", default="balanced", choices=["premium", "balanced", "economy", "fast"])
    s.add_argument("--improve", type=int, default=1, help="revision rounds with the writer")
    s.add_argument("--out", help="directory for pack.json, report.md and per-format files")
    s.add_argument("--json", action="store_true"), s.add_argument("--quiet", action="store_true")
    s.set_defaults(fn=cmd_forge)

    s = sub.add_parser("guru", help="content strategy plan")
    gs = s.add_subparsers(dest="guru_cmd", required=True)
    x = gs.add_parser("plan"); _brief_flags(x)
    x.add_argument("--weeks", type=int, default=4), x.add_argument("--posts-per-week", type=int, default=5), x.add_argument("--channels")
    x.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_guru)

    s = sub.add_parser("audit", help="check existing copy against the claims profile (exit code 1 when it has errors)")
    s.add_argument("files", nargs="+", help="text files, or - for standard input")
    s.add_argument("--vertical", help="default: pbm"), s.add_argument("--lang", choices=["en", "cs"], help="default: detected")
    s.add_argument("--claims-profile", choices=["general", "wellness"]), s.add_argument("--brand")
    s.add_argument("--fact", action="append", help="a verified first-party fact the copy may state, repeatable")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("visibility", help="AI answer visibility from pasted answers (JSON)")
    s.add_argument("answers"), s.add_argument("--brand", required=True), s.add_argument("--competitors"), s.add_argument("--domains")
    s.add_argument("--lang", default="en", choices=["en", "cs"]), s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_visibility)

    s = sub.add_parser("serve", help="run the game with the local API")
    s.add_argument("--host", default="127.0.0.1"), s.add_argument("--port", type=int, default=8765)
    s.add_argument("--writer", default="auto", choices=["auto", "offline", "anthropic"]), s.add_argument("--page")
    s.add_argument("--allow-remote", action="store_true"), s.add_argument("--verbose", action="store_true")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("build-web", help="build the single-file game")
    s.add_argument("--out", default=str(ROOT / "web" / "dist" / "dopamine-king.html")), s.add_argument("--bundle")
    s.add_argument("--vertical", default="pbm", help="edition of the game: pbm (MITO LIGHT, default) or general")
    s.set_defaults(fn=cmd_build_web)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as err:   # network or environment problems should read like messages, not stack traces
        from .net import FetchError
        if isinstance(err, FetchError) or err.__class__.__name__ in ("BlockedByPolicy",):
            print(f"network/policy error: {err}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
