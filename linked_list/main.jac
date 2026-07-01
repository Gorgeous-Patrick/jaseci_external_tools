import os;

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
    has found: bool = false;

    can visit_item with Item entry {
        if here.value == self.target {
            self.found = true;
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
    print(f"root: {root.__jac__.id}");

    return [str(item.__jac__.id) for item in items];
}
