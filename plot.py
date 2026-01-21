import matplotlib.pyplot as plt
import networkx as nx

def plot_walkers_graph(
    G,
    layout="dot",
    figsize=(12, 8),
    node_size=800,
    font_size=10,
    arrow_size=15,
    save_path=None,
):
    """
    Plot a NetworkX graph with selectable layout and optional saving to file.

    Parameters
    ----------
    G : networkx.Graph or networkx.MultiDiGraph

    layout : str or callable
        Layout options:
            "dot", "neato", "twopi"  -> Graphviz layouts
            "spring", "kamada_kawai", "shell", "circular"
        Or a custom function: fn(G) -> pos dict.

    figsize : tuple
        Size of the figure.

    node_size : int
        Node size.

    font_size : int
        Label font size.

    arrow_size : int
        Arrow size.

    save_path : str or None
        If provided, saves the figure to this path (png/pdf/svg/...).
        Example: "graph.png"
    """

    plt.figure(figsize=figsize)

    # --------------------------------------
    # Select Layout
    # --------------------------------------
    if callable(layout):
        pos = layout(G)

    else:
        layout = layout.lower()

        if layout in ("dot", "neato", "twopi"):
            try:
                pos = nx.nx_agraph.graphviz_layout(G, prog=layout)
            except Exception:
                print(f"[Warning] Graphviz layout '{layout}' not available. Using spring layout.")
                pos = nx.spring_layout(G, seed=42)

        elif layout == "spring":
            pos = nx.spring_layout(G, seed=42)

        elif layout == "kamada_kawai":
            pos = nx.kamada_kawai_layout(G)

        elif layout == "shell":
            pos = nx.shell_layout(G)

        elif layout == "circular":
            pos = nx.circular_layout(G)

        else:
            raise ValueError(f"Unknown layout '{layout}'")

    # --------------------------------------
    # Simplify MultiDiGraph for drawing
    # --------------------------------------
    H = nx.DiGraph()
    H.add_nodes_from(G.nodes())
    for u, v in G.edges():
        H.add_edge(u, v)

    # --------------------------------------
    # Drawing
    # --------------------------------------
    nx.draw(
        H,
        pos,
        with_labels=True,
        arrows=True,
        node_size=node_size,
        font_size=font_size,
        node_color="lightblue",
        arrowstyle="->",
        arrowsize=arrow_size,
    )

    plt.title(f"Walker Graph (layout='{layout}')")
    plt.tight_layout()

    # --------------------------------------
    # Save to file if requested
    # --------------------------------------
    if save_path is not None:
        plt.savefig(save_path, dpi=300)
        print(f"Saved graph image to: {save_path}")

    plt.close()
