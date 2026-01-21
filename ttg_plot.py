import plot
import ttg
import json

with open("/home/patrickli/Space/jaseci/load_feed_ttg.json", "r") as json_file:
    json_str = json.load(json_file)

graphs = ttg.walkers_to_multidigraph_list(json_str)

for idx, graph in enumerate(graphs):
    plot.plot_walkers_graph(graph, layout="dot", save_path=f"TTG_{idx}.png")
