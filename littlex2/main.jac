import random;
import os;
import json;
import from util { append_to_json_list }
node Profile {
    has id: int;
}

node Tweet {
    has id: int;
}

edge Follow {}
edge Post {}

walker LoadFeed {
    has visiting_neighbors: bool = False;
    has visited: int = 0;

    can load with Profile entry {
        self.visited += 1;
        if (not self.visiting_neighbors) {
            self.visiting_neighbors = True;
            visit [->:Post:->];
            visit [->:Follow:->];
        } else {
            visit [->:Post:->];
        }
    }

    can calc with Tweet entry {
        self.visited += 1;
        # print(here.id);
    }
}

def create_node() -> list[str] {
    random.seed(0);
    nodes = [];
    NODE_NUM = int(os.environ.get("JAC_NODE_NUM"));
    EDGE_NUM = int(os.environ.get("JAC_EDGE_NUM"));
    if (EDGE_NUM is None) {
        exit(1);
    }
    TWEET_NUM = int(os.environ.get("JAC_TWEET_NUM"));
    TWEET_NUM = 1;

    root_id = root.__jac__.id;
    root.__jac__.persistent = True;

    for i in range(NODE_NUM) {
        p = Profile(id=i);
        p.__jac__.persistent = True;
        p.__jac__.root = root_id;
        nodes.append(p);
        root +>: Post :+> nodes[i];
        for j in range(TWEET_NUM) {
            t = Tweet(id=NODE_NUM + TWEET_NUM * i + j);
            t.__jac__.persistent = True;
            t.__jac__.root = root_id;
            nodes[i] +>: Post :+> t;
        }
        print(f"Created node {i} (Total {NODE_NUM}) with tweets {TWEET_NUM}");
    }

    available_edges = set();

    for i in range(NODE_NUM) {
        for j in range(NODE_NUM) {
            if (i == j) {
                continue;
            }
            available_edges.add((i, j));
        }
    }

    for i in range(EDGE_NUM) {
        (src, dst) = random.choice(list(available_edges));
        nodes[src] +>: Follow :+> nodes[dst];
        available_edges.remove((src, dst));
        print(f"Created edge {i} (Total {EDGE_NUM}) from {src} to {dst}");
    }
    # Mark root anchor updated so topology index gets persisted to L3.
    # set_topology_index modifies the anchor directly without setting is_updated.
    root.__jac__.is_updated = True;

    print(f"{root.__jac__.id}");
    return [str(n.__jac__.id) for n in nodes];
}
