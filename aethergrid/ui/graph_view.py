"""Interactive Energy Opportunity Graph view (PART AG). Node position comes
from the synthetic site layout (graph/features.py:synthetic_coordinates)
so it's stable across reruns instead of a force-layout that jitters."""
from __future__ import annotations

import networkx as nx
import plotly.graph_objects as go

STATUS_ORDER = ["REJECTED", "DISCOVERED", "TECHNICALLY_PLAUSIBLE", "ECONOMICALLY_VIABLE", "RECOMMENDED"]


def energy_opportunity_graph_figure(G: nx.Graph) -> go.Figure:
    fig = go.Figure()
    pos = {n: (d["x_m"], d["y_m"]) for n, d in G.nodes(data=True)}

    for u, v, d in G.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        width = 1 + 4 * d.get("score", 0) if d.get("status") in ("ECONOMICALLY_VIABLE", "RECOMMENDED") else 1
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1], mode="lines",
            line=dict(width=width, color=d.get("color", "#9aa0a6")),
            hoverinfo="text",
            text=f"{u} <-> {v}<br>kind={d.get('kind')}<br>status={d.get('status')}<br>"
                 f"mechanism={d.get('mechanism')}<br>score={d.get('score', 0):.2f}",
            showlegend=False,
        ))

    node_x = [pos[n][0] for n in G.nodes()]
    node_y = [pos[n][1] for n in G.nodes()]
    sizes = [12 + 0.05 * G.nodes[n].get("peak_kw", 0) for n in G.nodes()]
    colors = [G.nodes[n].get("criticality", 0.3) for n in G.nodes()]
    labels = [f"{n}<br>{G.nodes[n].get('building_type','')}<br>peak={G.nodes[n].get('peak_kw',0):.0f}kW"
              for n in G.nodes()]

    fig.add_trace(go.Scatter(
        x=node_x, y=node_y, mode="markers+text", text=list(G.nodes()), textposition="top center",
        hoverinfo="text", hovertext=labels,
        marker=dict(size=sizes, color=colors, colorscale="YlOrRd", showscale=True,
                    colorbar=dict(title="criticality"), line=dict(width=1, color="#333")),
        showlegend=False,
    ))

    fig.update_layout(
        title="Energy Opportunity Graph", height=460, margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(visible=False), yaxis=dict(visible=False), template="plotly_white",
    )
    return fig
