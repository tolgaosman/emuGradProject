""" reporter.py — Output artifact generation. """
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from .matrix import ComparisonMatrix
 
class ReportGenerator:
    def generate(self, matrix, output_dir, threshold=0.70):
        os.makedirs(output_dir, exist_ok=True)
        return {
            "csv":     self._csv(matrix, output_dir),
            "heatmap": self._heatmap(matrix, output_dir, threshold),
            "html":    self._html(matrix, output_dir, threshold),
        }
 
    def _csv(self, m, out):
        p = os.path.join(out, "similarity_matrix.csv")
        open(p,"w").write(m.to_csv())
        return p
 
    def _heatmap(self, m, out, thr):
        df = pd.DataFrame(m.as_numpy(), index=m.names, columns=m.names)
        n  = len(m.names)
        fig, ax = plt.subplots(figsize=(max(6,n), max(5,n)))
        sns.heatmap(df, annot=True, fmt=".2f", cmap="YlOrRd",
                    vmin=0, vmax=1, ax=ax, linewidths=0.5)
        for i in range(n):
            for j in range(n):
                if i != j and m.get(i,j) >= thr:
                    ax.add_patch(plt.Rectangle((j,i),1,1,
                        fill=False, edgecolor="red", lw=2))
        p = os.path.join(out, "similarity_heatmap.png")
        plt.tight_layout()
        plt.savefig(p, dpi=300, bbox_inches="tight")
        plt.close(); return p
 
    def _html(self, m, out, thr):
        rows = ""
        for pr in m.get_flagged(thr):
            c = "#c0392b" if pr["score"] >= 0.90 else "#e67e22"
            rows += (f'<tr><td>{pr["file_a"]}</td><td>{pr["file_b"]}</td>'
                     f'<td style="color:{c}">{pr["score"]:.4f}</td>'
                     f"<td>Flagged for review</td></tr>")
        html = ('<!DOCTYPE html><html><head><meta charset="UTF-8">'
                '<title>Similarity Report</title><style>'
                'body{font-family:Arial;margin:2em}'
                'table{border-collapse:collapse;width:100%}'
                'th,td{border:1px solid #ccc;padding:8px 12px}'
                'th{background:#2E4057;color:#fff}'
                f'</style></head><body><h1>Similarity Report</h1>'
                f'<p>Threshold: {thr:.2f} | Flagged: {len(m.get_flagged(thr))}</p>'
                f'<table><tr><th>File A</th><th>File B</th>'
                f'<th>Score</th><th>Status</th></tr>{rows}</table>'
                '</body></html>')
        p = os.path.join(out, "comparison_report.html")
        open(p,"w",encoding="utf-8").write(html)
        return p
