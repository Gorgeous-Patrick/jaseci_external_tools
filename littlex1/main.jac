import random;
import os;
import json;
import from util { append_to_json_list }
import from jaclang.pycore.runtime {JacRuntime}
node Profile {
    has id: int;
}

edge Follow {}

walker LoadFeed {
    has visiting_neighbors: bool = False;
    has visited: int = 0;

    can load with Profile entry {
        print("RUNNNN");
        self.visited += 1;
        if (self.visited >= 100) {
            return;
        }
        print(f"{here.__jac__.id}");
        if (not self.visiting_neighbors) {
            self.visiting_neighbors = True;
            visit [->:Follow:->];
        } else {
        }
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
    for i in range(NODE_NUM) {
        nodes.append(Profile(id=i));
        root ++> nodes[i];
        print(f"Created node {i} (Total {NODE_NUM}) with tweets");
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
    print(f"{root.__jac__.id}");
    return [str(n.__jac__.id) for n in nodes];
}
