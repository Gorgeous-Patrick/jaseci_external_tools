import os;

node Profile {
    has id: int;
}

node Tweet {
    has id: int;
}

edge Follow {}
edge Post {}

walker LoadFeed {
    has visited: int = 0;

    can load with Profile entry {
        visit [->:Follow:->];
        visit [->:Post:->];
    }

    can calc with Tweet entry {
        self.visited += 1;
        report self;
        if self.visited >= 500 {
            disengage;
        }
    }
}

def create_node() -> list[str] {
    nodes: dict[int, Profile] = {};
    edges: list[tuple[int, int]] = [];

    # Read edge list from file
    edge_file = "edges.txt";

    TWEET_NUM = int(os.environ.get("JAC_TWEET_NUM", "10"));

    # Parse edge list file
    with open(edge_file, "r") as f {
        for line in f {
            line = line.strip();
            if not line {
                continue;
            }
            parts = line.split();
            if len(parts) >= 2 {
                src = int(parts[0]);
                dst = int(parts[1]);
                edges.append((src, dst));
            }
        }
    }

    # Collect unique node IDs
    node_ids: set[int] = set();
    for (src, dst) in edges {
        node_ids.add(src);
        node_ids.add(dst);
    }

    print(f"Loaded {len(edges)} edges, {len(node_ids)} unique nodes from {edge_file}");

    # Create Profile nodes
    tweet_counter = 0;
    for node_id in sorted(node_ids) {
        p = Profile(id=node_id);
        nodes[node_id] = p;
        root ++> p;

        # Create tweets for each profile
        for j in range(TWEET_NUM) {
            t = Tweet(id=tweet_counter);
            tweet_counter += 1;
            p +>: Post :+> t;
        }

        if len(nodes) % 1000 == 0 {
            print(f"Created {len(nodes)} nodes...");
        }
    }

    print(f"Created {len(nodes)} Profile nodes with {TWEET_NUM} tweets each");

    # Create Follow edges
    edge_count = 0;
    for (src, dst) in edges {
        if src in nodes and dst in nodes {
            nodes[src] +>: Follow :+> nodes[dst];
            edge_count += 1;
            if edge_count % 10000 == 0 {
                print(f"Created {edge_count} edges...");
            }
        }
    }

    print(f"Created {edge_count} Follow edges");
    print(f"root: {root.__jac__.id}");

    return [str(n.__jac__.id) for n in nodes.values()];
}
