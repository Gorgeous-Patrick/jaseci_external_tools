import networkx as nx

def walkers_to_multidigraph_list(data):
    """
    Convert a list of walker-tree dicts into a list of NetworkX MultiDiGraphs.

    Parameters
    ----------
    data : list[dict]
        Parsed JSON-like structure. Each element in `data` is the root
        of a separate TTG.

    Returns
    -------
    graphs : list[networkx.MultiDiGraph]
        One MultiDiGraph per TTG. Nodes are integers (node['id']),
        edges are parent->child, no attributes stored.
    """
    graphs: list[nx.MultiDiGraph] = []

    for root in data:
        G = nx.MultiDiGraph()

        def process(node_dict, parent_id=None):
            node_id = node_dict["node"]["id"]

            # Ensure node exists (no attributes stored)
            G.add_node(node_id)

            # Add edge if parent exists
            if parent_id is not None:
                G.add_edge(parent_id, node_id)

            # Recurse into children
            for child in node_dict.get("children", []):
                process(child, parent_id=node_id)

        # Build graph for this root TTG
        process(root, parent_id=None)
        graphs.append(G)

    return graphs
