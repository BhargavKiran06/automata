from main import length_curve, LengthReq

for lang in ["anbn", "div_by_3"]:
    out = length_curve(LengthReq(language=lang, n=40, max_len=8))
    print(lang, "| learned states:", out["states"])
    for p in out["points"][::3]:
        print("  length", p["length"], "recall", p["recall"], "specificity", p["specificity"])

