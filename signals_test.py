from signals import groq_signal, stylometric_signal, combine_scores

tests = {
    "CLEAR AI (rich)": """Artificial intelligence represents a transformative paradigm
shift in modern society. It is important to note that while the benefits are numerous,
it is equally essential to consider the ethical implications. Furthermore, stakeholders
across various sectors must collaborate to ensure responsible deployment.""",

    "CLEAR HUMAN (casual)": """ok so i finally tried that new ramen place downtown and
honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and
i was thirsty for like three hours after. probably won't go back unless someone drags me.""",

    "BORDERLINE: formal HUMAN": """The relationship between monetary policy and asset
price inflation has been extensively studied in the literature. Central banks face a
fundamental tension between their mandate for price stability and the unintended
consequences of prolonged low interest rates on equity and real estate valuations.""",

    "BORDERLINE: edited AI": """I've been thinking a lot about remote work lately. There
are genuine tradeoffs flexibility and no commute on one side, isolation and blurred
work-life boundaries on the other. Studies show productivity varies widely by individual.""",
}

for label, text in tests.items():
    llm = groq_signal(text)
    stylo = stylometric_signal(text)
    conf, attr = combine_scores(llm, stylo)
    print(f"{label}")
    print(f"   llm={llm}  stylo={stylo}  ->  confidence={conf}  [{attr}]")
    print()