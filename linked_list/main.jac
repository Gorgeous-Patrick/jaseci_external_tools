import os;
import oop_capre;

node Item {
    has value: int;
    has index: int;
}

edge Next {}

# Traverse the list and report every value in order
walker Traverse {
    has visited: int = 0;

    can visit_item with Item entry {
        self.visited += 1;
        report here.value;
        if self.visited >= 10000 {
            disengage;
        }
        visit [->:Next:->];
    }
}

# Sum all values in the list
walker Sum {
    has total: int = 0;

    can visit_item with Item entry {
        self.total += here.value;
        visit [->:Next:->];
    }

    can done with Item exit {
        report self.total;
    }
}

# Find first item matching a value, report its index
walker Find {
    has target: int;
    has found: bool = False;

    can visit_item with Item entry {
        if here.value == self.target {
            self.found = True;
            report here;
            disengage;
        }
        visit [->:Next:->];
    }
}

def setup_graph() -> list[str] {
    LIST_SIZE = int(os.environ.get("JAC_LIST_SIZE", "100"));

    head: Item = Item(value=0, index=0);
    root ++> head;

    prev = head;
    items: list[Item] = [head];

    for i in range(1, LIST_SIZE) {
        curr = Item(value=i, index=i);
        prev +>: Next :+> curr;
        prev = curr;
        items.append(curr);

        if i % 1000 == 0 {
            print(f"Created {i} items...");
        }
    }

    print(f"Built linked list of {LIST_SIZE} items");
    print(f"root: {oop_capre.jac_id(root)}");

    return [oop_capre.jac_id(item) for item in items];
}

def oop_traverse(
    start_id: str,
    prefetch_limit: int = 0,
    visit_limit: int = 10000,
    policy: str = "none",
    postgres_uri: str = "",
    access_log: str = "",
    actual_file: str = "",
    prefetch_file: str = "",
    profile_dir: str = "",
    profile_csv: str = "",
    include_metrics: bool = False
) -> any {
    run = oop_capre.OopTraversal(
        start_id,
        prefetch_limit,
        visit_limit,
        policy,
        postgres_uri,
        profile_dir,
        profile_csv
    );
    current = run.load_start();
    reports: list[int] = [];

    for i in range(visit_limit) {
        if current is None {
            break;
        }

        value = current.value;
        reports.append(value);
        run.record_value(value);

        if len(reports) < visit_limit {
            run.maybe_prefetch(current.id);
            current = run.next_item(current);
        }
    }

    return run.finish_response(
        reports,
        access_log,
        actual_file,
        prefetch_file,
        include_metrics
    );
}
