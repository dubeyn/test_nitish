import pandas as pd

df = pd.read_csv("Paytm.csv", encoding="unicode_escape")
print(df.head(5))


import sweetviz as sv
report = sv.analyze(df)
report.show_html("Paytm_report.html")
