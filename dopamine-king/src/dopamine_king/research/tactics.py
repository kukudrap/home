"""Content tactics, in English and Czech, that the evidence ledger links studies to.

Each summary is phrased as a claim; an ``EvidenceLink`` direction says whether a study supports
that claim. Tactics with manipulation risk carry an ethics note.
"""
from __future__ import annotations

from .models import Tactic

_DEFS: list[tuple[str, str, str, str, str, str, str, str]] = [
    # (id, driver, name_en, name_cs, summary_en, summary_cs, ethics_en, ethics_cs)
    (
        "curiosity-gap", "curiosity",
        "Curiosity gap", "Mezera zvědavosti",
        "Make the reader aware of a specific piece of missing information, then deliver it. "
        "Information-gap theory describes curiosity as a feeling of deprivation caused by a gap between "
        "what we know and what we want to know.",
        "Ukažte čtenáři konkrétní informaci, která mu chybí, a pak mu ji doručte. Teorie informační mezery "
        "popisuje zvědavost jako pocit nedostatku, který vzniká z rozdílu mezi tím, co víme, a tím, co chceme vědět.",
        "Keep the promise. A gap the content never closes is clickbait and spends the audience's trust.",
        "Slib dodržte. Mezera, kterou obsah nikdy nezaplní, je clickbait a promarňuje důvěru publika.",
    ),
    (
        "anticipation-payoff", "curiosity",
        "Anticipation and payoff", "Očekávání a odměna",
        "Build a short, honest anticipation (a teaser, a countdown, a promised answer) and deliver a payoff "
        "that matches it. Looking forward to a reward and receiving it are two distinct moments, and both can be rewarding.",
        "Vybudujte krátké, poctivé očekávání (upoutávku, odpočet, slíbenou odpověď) a doručte odměnu, která mu "
        "odpovídá. Těšit se na odměnu a získat ji jsou dva různé okamžiky a oba mohou být příjemné.",
        "Do not stretch the wait artificially or hide the payoff behind needless clicks.",
        "Čekání neprotahujte uměle a odměnu neschovávejte za zbytečná kliknutí.",
    ),
    (
        "prediction-error", "surprise",
        "Prediction error (surprise)", "Predikční chyba (překvapení)",
        "Something that violates expectations tends to get noticed. In animals, dopamine neurons signal the gap "
        "between expected and received reward, the best-known neural account of surprise.",
        "Co porušuje očekávání, si lidé obvykle všimnou. U zvířat dopaminové neurony signalizují rozdíl mezi "
        "očekávanou a získanou odměnou, což je nejznámější neurální vysvětlení překvapení.",
        "Surprise must be honest. Novelty is also what makes false news spread, so never invent the unexpected.",
        "Překvapení musí být poctivé. Novost je také to, co šíří falešné zprávy, proto nikdy nevymýšlejte nečekané.",
    ),
    (
        "emotional-arousal", "emotion",
        "Emotional arousal", "Emoční aktivace",
        "Content that evokes high-arousal emotions such as awe, anger or anxiety is shared more than content that "
        "evokes low-arousal emotions such as sadness.",
        "Obsah, který vyvolává emoce s vysokou aktivací (úžas, hněv, úzkost), se sdílí častěji než obsah "
        "vyvolávající emoce s nízkou aktivací, například smutek.",
        "Do not manufacture outrage or fear to win clicks. Unearned emotion erodes trust and can hurt readers.",
        "Nevyrábějte pobouření ani strach kvůli prokliku. Nezasloužená emoce podkopává důvěru a může čtenářům ublížit.",
    ),
    (
        "negativity-bias", "emotion",
        "Negativity bias", "Negativní zkreslení",
        "Negative information tends to weigh more than positive information, but online sharing is not simply a "
        "matter of negativity: in one large study positive articles were shared more often, and only high-arousal "
        "negative emotions such as anger and anxiety boosted sharing.",
        "Negativní informace mívají větší váhu než pozitivní, ale sdílení online není jen otázka negativity: "
        "v jedné velké studii se pozitivní články sdílely častěji a sdílení podporovaly jen negativní emoce "
        "s vysokou aktivací, například hněv a úzkost.",
        "Fear and outrage framing can mislead and harm. Do not exaggerate threats to get attention.",
        "Rámování strachem a pobouřením může klamat a škodit. Nepřehánějte hrozby kvůli pozornosti.",
    ),
    (
        "social-currency", "relevance",
        "Social currency", "Sociální měna",
        "People share what makes them look interesting or well informed. Remarkable, insider or identity-relevant "
        "content gives them something to talk about.",
        "Lidé sdílejí to, díky čemu působí zajímavě nebo informovaně. Pozoruhodný, zasvěcený nebo identitě blízký "
        "obsah jim dává o čem mluvit.",
        "Do not push status anxiety or fear of missing out to drive sharing.",
        "Nepodporujte sdílení tlakem na status ani strachem, že něco zmeškáte.",
    ),
    (
        "triggers-cues", "relevance",
        "Triggers and cues", "Spouštěče a podněty",
        "Tie content to something the audience meets often (a time of day, a place, a routine) so the environment "
        "keeps reminding them of it and conversation continues over time.",
        "Svažte obsah s něčím, s čím se publikum setkává často (denní doba, místo, rutina), aby mu to prostředí "
        "průběžně připomínalo a rozhovor o něm pokračoval.",
        "Reminders should serve the user: avoid notification spam.",
        "Připomínky mají sloužit uživateli: vyhněte se zahlcování upozorněními.",
    ),
    (
        "social-proof", "relevance",
        "Social proof", "Sociální důkaz",
        "People look to what others do and approve of when they decide. Honest signals such as real counts and real "
        "testimonials can increase trust and action.",
        "Při rozhodování se lidé dívají na to, co dělají a schvalují druzí. Poctivé signály, například skutečné "
        "počty a skutečná doporučení, mohou zvýšit důvěru i ochotu jednat.",
        "Use only real numbers and real customers. Fake reviews and inflated counts are deceptive and often illegal.",
        "Používejte jen skutečná čísla a skutečné zákazníky. Falešné recenze a nafouknuté počty jsou klamavé a často nezákonné.",
    ),
    (
        "practical-value", "utility",
        "Practical value", "Praktická užitečnost",
        "Practically useful content (tips, how-tos, checklists, tools that save time or money) is more likely to be shared.",
        "Prakticky užitečný obsah (tipy, návody, checklisty, nástroje šetřící čas nebo peníze) se sdílí s větší pravděpodobností.",
        "Useful means accurate: do not present guesses as proven advice.",
        "Užitečný znamená přesný: odhady nevydávejte za ověřené rady.",
    ),
    (
        "cognitive-fluency", "fluency",
        "Cognitive fluency", "Kognitivní plynulost",
        "Content that is easy to read and process tends to be judged more favourably. Plain words, short sentences "
        "and a clear layout lower the effort the reader has to spend.",
        "Obsah, který se snadno čte a zpracovává, bývá hodnocen příznivěji. Jednoduchá slova, krátké věty a přehledné "
        "rozvržení snižují námahu, kterou musí čtenář vynaložit.",
        "Fluency can make weak or false claims feel true. Use it to clarify, not to disguise.",
        "Plynulost může způsobit, že slabá nebo nepravdivá tvrzení působí věrohodně. Používejte ji k vysvětlení, ne k zakrytí.",
    ),
    (
        "numbers-specificity", "fluency",
        "Numbers and specificity", "Čísla a konkrétnost",
        "Concrete numbers and specific details are commonly advised because they are easier to picture and check "
        "than vague wording ('seven steps' rather than 'some tips'). The ledger holds no direct test of this yet.",
        "Konkrétní čísla a podrobnosti se běžně doporučují, protože se dají snáz představit a ověřit než vágní "
        "formulace ('sedm kroků' místo 'pár tipů'). Registr studií zatím neobsahuje její přímý test.",
        "Numbers must be real and sourced. Fake precision is deception.",
        "Čísla musí být skutečná a doložená. Falešná přesnost je klam.",
    ),
    (
        "headline-questions", "curiosity",
        "Question headlines", "Titulky s otázkou",
        "A question in the headline can open an information gap, but only if the content answers it. Whether it wins "
        "more clicks depends on audience and topic and should be tested.",
        "Otázka v titulku může otevřít informační mezeru, ale jen tehdy, když na ni obsah odpoví. Zda získá víc "
        "prokliků, závisí na publiku a tématu a mělo by se to otestovat.",
        "Do not ask a question whose honest answer is no just to bait the click.",
        "Neptejte se otázkou, na kterou je poctivá odpověď ne, jen abyste vylákali proklik.",
    ),
    (
        "storytelling", "emotion",
        "Storytelling", "Vyprávění příběhu",
        "A story with characters and a clear arc can absorb the reader, and readers who are absorbed tend to adopt "
        "the beliefs the story implies.",
        "Příběh s postavami a jasným obloukem může čtenáře pohltit a pohlcení čtenáři mívají sklon přijmout "
        "přesvědčení, která příběh předpokládá.",
        "Stories can persuade without evidence. Do not use invented anecdotes as proof.",
        "Příběhy mohou přesvědčovat i bez důkazů. Vymyšlené historky nepoužívejte jako důkaz.",
    ),
    (
        "personalization", "relevance",
        "Personalisation", "Personalizace",
        "Matching a message to the audience's interests or traits can improve response, but it needs data about "
        "the audience and care in using it.",
        "Přizpůsobení sdělení zájmům nebo rysům publika může zlepšit odezvu, vyžaduje ale data o publiku a "
        "opatrnost při jejich použití.",
        "Use only data people knowingly shared, respect consent and privacy law, and do not target vulnerabilities.",
        "Používejte jen data, která lidé vědomě poskytli, respektujte souhlas a ochranu soukromí a necilte na zranitelná místa.",
    ),
    (
        "variable-reward", "game",
        "Variable reward", "Proměnlivá odměna",
        "Unpredictable (variable-ratio) reward schedules sustain responding in animal experiments. How far this "
        "carries over to content and apps is unproven.",
        "Nepředvídatelné (variabilně poměrové) plány odměn udržují reakce v pokusech na zvířatech. Do jaké míry to "
        "platí pro obsah a aplikace, není prokázáno.",
        "This is the mechanism behind compulsive feeds and slot machines. Never use it to build compulsion; give "
        "users control and honest limits.",
        "Toto je mechanismus kompulzivních feedů a výherních automatů. Nikdy ho nepoužívejte k vytváření nutkání; "
        "dejte uživatelům kontrolu a poctivé limity.",
    ),
    (
        "streaks-loss-aversion", "game",
        "Streaks and loss aversion", "Série a averze ke ztrátě",
        "People weigh losses more heavily than equal gains, so a streak that can be lost feels valuable. In prospect "
        "theory this is loss aversion; how strongly it applies to streak mechanics is not established.",
        "Lidé přikládají ztrátám větší váhu než stejně velkým ziskům, a proto série, o kterou lze přijít, působí "
        "cenně. V teorii vyhlídek se tomu říká averze ke ztrátě; jak silně platí u sérií, není prokázáno.",
        "Streaks that punish rest or guilt-trip users harm wellbeing. Offer freezes and forgiveness.",
        "Série, které trestají odpočinek nebo vyvolávají pocit viny, škodí pohodě. Nabídněte pauzy a odpuštění.",
    ),
    (
        "gamification-points-badges", "game",
        "Points, badges and leaderboards", "Body, odznaky a žebříčky",
        "Game elements such as points, badges and leaderboards can improve engagement and learning outcomes in some "
        "contexts. Effects are typically small to moderate and depend on the context and the users.",
        "Herní prvky jako body, odznaky a žebříčky mohou v některých kontextech zlepšit zapojení a výsledky učení. "
        "Účinky bývají malé až střední a závisejí na kontextu a uživatelích.",
        "Do not turn points into pressure. Rankings can demotivate many users and should be optional.",
        "Z bodů nedělejte tlak. Žebříčky mohou řadu uživatelů odradit a měly by být volitelné.",
    ),
    (
        "intrinsic-vs-extrinsic-motivation", "game",
        "Intrinsic vs extrinsic motivation", "Vnitřní a vnější motivace",
        "Expected, tangible rewards tend to undermine intrinsic motivation (the overjustification effect). Design "
        "rewards that support the value of the activity itself instead of replacing it.",
        "Očekávané hmotné odměny mívají tendenci oslabovat vnitřní motivaci (efekt nadměrného zdůvodnění). "
        "Navrhujte odměny, které podporují vlastní hodnotu činnosti, místo aby ji nahrazovaly.",
        "Avoid reward schemes that crowd out genuine interest.",
        "Vyhněte se systémům odměn, které vytlačují skutečný zájem.",
    ),
    (
        "scarcity-urgency", "emotion",
        "Scarcity and urgency", "Nedostatek a naléhavost",
        "Limited supply or limited time makes an offer feel more valuable and pushes people to act sooner.",
        "Omezená zásoba nebo omezený čas činí nabídku cennější a pobízí lidi, aby jednali dřív.",
        "Use only truthful scarcity: real stock and real deadlines. Fake countdowns and invented shortages are "
        "deceptive and may be illegal.",
        "Používejte jen pravdivý nedostatek: skutečné zásoby a skutečné termíny. Falešná odpočítávání a vymyšlené "
        "nedostatky jsou klamavé a mohou být nezákonné.",
    ),
    (
        "dopamine-myth", "integrity",
        "The dopamine myth", "Mýtus o dopaminu",
        "Dopamine is not a simple pleasure chemical. It is tied to wanting, anticipation and prediction error, which "
        "is why 'dopamine hits' is a misleading way to describe engagement.",
        "Dopamin není jednoduchá chemická látka potěšení. Souvisí s toužením, očekáváním a predikční chybou, a "
        "proto je výraz 'dávky dopaminu' zavádějící popis zapojení.",
        "Do not use neuroscience words to dress up manipulation. Say what the content does, not that it hacks the brain.",
        "Neurovědní slova nepoužívejte k ozdobení manipulace. Řekněte, co obsah dělá, ne že hackuje mozek.",
    ),
    (
        "video-hook-first-seconds", "structure",
        "Video hook in the first seconds", "Háček v prvních vteřinách videa",
        "Open a video with its most compelling moment or promise so viewers know within seconds why to stay. The "
        "ledger holds no direct test of this yet; measure retention with your own tests.",
        "Začněte video nejsilnějším momentem nebo příslibem, aby diváci během vteřin věděli, proč zůstat. Registr "
        "studií zatím neobsahuje její přímý test; udržení diváků měřte vlastními testy.",
        "The hook must be in the video. A hook that misrepresents the content costs trust.",
        "Háček musí být ve videu skutečně obsažen. Háček, který zkresluje obsah, stojí důvěru.",
    ),
    (
        "ab-testing-basics", "testing",
        "A/B testing basics", "Základy A/B testování",
        "Randomly split traffic between variants, choose the metric and sample size in advance, and judge the result "
        "with the planned statistics. Controlled experiments are the most reliable way to learn what works for your "
        "own audience.",
        "Provoz náhodně rozdělte mezi varianty, metriku a velikost vzorku zvolte předem a výsledek posuzujte "
        "plánovanou statistikou. Kontrolované experimenty jsou nejspolehlivější způsob, jak zjistit, co funguje u "
        "vašeho publika.",
        "Do not run experiments that could harm users, and be open about how data is used.",
        "Nespouštějte experimenty, které mohou uživatelům uškodit, a otevřeně říkejte, jak se data používají.",
    ),
    (
        "ab-testing-peeking", "testing",
        "Peeking at A/B tests", "Nahlížení do A/B testů",
        "Checking a test repeatedly and stopping as soon as it looks significant inflates false positives. Fix the "
        "sample size in advance or use sequential methods designed for continuous monitoring.",
        "Opakované kontrolování testu a zastavení ve chvíli, kdy vypadá významně, zvyšuje počet falešně pozitivních "
        "výsledků. Velikost vzorku stanovte předem nebo použijte sekvenční metody určené pro průběžné sledování.",
        "Do not report a winner you stopped early as a proven result.",
        "Vítěze, kterého jste zastavili předčasně, nevydávejte za prokázaný výsledek.",
    ),
    (
        "geo-cite-sources", "geo",
        "GEO: cite sources", "GEO: odkazy na zdroje",
        "Citing credible sources in your content improved its visibility in generative engine answers in one benchmark.",
        "Odkazy na důvěryhodné zdroje v obsahu zlepšily v jednom srovnávacím testu jeho viditelnost v odpovědích "
        "generativních vyhledávačů.",
        "Cite only sources you have read and that say what you claim.",
        "Odkazujte jen na zdroje, které jste přečetli a které říkají to, co tvrdíte.",
    ),
    (
        "geo-statistics", "geo",
        "GEO: add statistics", "GEO: přidání statistik",
        "Adding relevant statistics improved visibility in generative engine answers in one benchmark.",
        "Přidání relevantních statistik zlepšilo v jednom srovnávacím testu viditelnost v odpovědích generativních "
        "vyhledávačů.",
        "Use only real, sourced numbers. Invented statistics are fabrication, and generative engines may repeat them.",
        "Používejte jen skutečná čísla s uvedeným zdrojem. Vymyšlené statistiky jsou fabulace a generativní "
        "vyhledávače je mohou opakovat.",
    ),
    (
        "geo-quotations", "geo",
        "GEO: add quotations", "GEO: citáty",
        "Adding quotations from credible people or documents improved visibility in generative engine answers in one "
        "benchmark.",
        "Přidání citátů důvěryhodných osob nebo dokumentů zlepšilo v jednom srovnávacím testu viditelnost v "
        "odpovědích generativních vyhledávačů.",
        "Quote accurately and with permission where needed. Never invent a quote or attribute words to someone who "
        "did not say them.",
        "Citujte přesně a tam, kde je třeba, se souhlasem. Citáty nikdy nevymýšlejte a nepřipisujte slova někomu, "
        "kdo je neřekl.",
    ),
    (
        "geo-keyword-stuffing", "geo",
        "GEO: keyword stuffing (does not help)", "GEO: nacpávání klíčových slov (nepomáhá)",
        "Repeating keywords did not help visibility in generative engine answers in one benchmark. Write for the "
        "reader and the question instead.",
        "Opakování klíčových slov v jednom srovnávacím testu nepomohlo viditelnosti v odpovědích generativních "
        "vyhledávačů. Pište raději pro čtenáře a jeho otázku.",
        "Keyword stuffing can also breach search spam policies.",
        "Nacpávání klíčových slov může také porušovat spamové zásady vyhledávačů.",
    ),
    (
        "answer-first-structure", "structure",
        "Answer-first structure", "Struktura s odpovědí na začátku",
        "Put the direct answer in the first lines, then explain, so both readers and answer engines find it "
        "immediately. The ledger holds no direct test of this yet.",
        "Přímou odpověď dejte hned na začátek a teprve potom vysvětlujte, aby ji čtenáři i odpovídající "
        "vyhledávače našli okamžitě. Registr studií zatím neobsahuje její přímý test.",
        "",
        "",
    ),
    (
        "eeat-experience", "integrity",
        "E-E-A-T and first-hand experience", "E-E-A-T a vlastní zkušenost",
        "Show first-hand experience, expertise, authority and trustworthiness: who wrote it, what they actually did, "
        "and how claims can be checked. Google describes this as guidance on content quality.",
        "Ukažte vlastní zkušenost, odbornost, autoritu a důvěryhodnost: kdo text napsal, co skutečně dělal a jak lze "
        "tvrzení ověřit. Google to popisuje jako vodítko kvality obsahu.",
        "Never fake credentials, reviews or hands-on experience.",
        "Nikdy nepředstírejte kvalifikaci, recenze ani vlastní zkušenost.",
    ),
    (
        "scaled-content-abuse", "integrity",
        "Scaled content abuse", "Zneužití hromadné tvorby obsahu",
        "Producing many low-value pages mainly to rank, however they are made (including with AI), can violate "
        "search spam policies.",
        "Hromadná tvorba mnoha stránek s nízkou hodnotou hlavně kvůli pořadí ve vyhledávání, ať už vznikají "
        "jakkoli (včetně umělé inteligence), může porušovat spamové zásady vyhledávačů.",
        "Scale only what is useful to people. Mass-produced filler wastes readers' time and risks penalties.",
        "Škálujte jen to, co lidem pomáhá. Hromadně vyráběná výplň plýtvá časem čtenářů a hrozí za ni postihy.",
    ),
]

TACTICS: dict[str, Tactic] = {
    d[0]: Tactic(
        id=d[0], driver=d[1], name_en=d[2], name_cs=d[3],
        summary_en=d[4], summary_cs=d[5], ethics_en=d[6], ethics_cs=d[7],
    )
    for d in _DEFS
}


def get_tactic(tactic_id: str) -> Tactic:
    """Return the tactic with this id; raises KeyError for an unknown id."""
    try:
        return TACTICS[tactic_id]
    except KeyError:
        raise KeyError(f"unknown tactic {tactic_id!r}") from None


def tactics_by_driver(driver: str) -> list[Tactic]:
    """Tactics for one driver, in definition order (empty for an unknown driver)."""
    return [t for t in TACTICS.values() if t.driver == driver]
