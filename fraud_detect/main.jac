import random;
import os;

node Account {
    has id: int;
    has balance: float;
    has tx_count: int = 0;
    has flagged: bool = false;
}

node Transaction {
    has id: int;
    has amount: float;
    has flagged: bool = false;
}

edge Sends {}
edge Receives {}

# Walker that detects fraud by inspecting accounts and their transactions.
# Flags:
#   - Accounts with tx_count > VELOCITY_THRESHOLD (high-velocity)
#   - Transactions with amount > AMOUNT_THRESHOLD (large-value)
#   - Transactions whose sender account is already flagged
walker FraudDetector {
    has visited: int = 0;
    has flagged_accounts: int = 0;
    has suspicious_txs: int = 0;

    can inspect_account with Account entry {
        self.visited += 1;
        if self.visited >= 2000 {
            disengage;
        }

        VELOCITY_THRESHOLD = int(os.environ.get("JAC_VELOCITY_THRESHOLD", "5"));
        if here.tx_count > VELOCITY_THRESHOLD {
            here.flagged = true;
            self.flagged_accounts += 1;
        }

        visit [->:Sends:->];
    }

    can inspect_tx with Transaction entry {
        AMOUNT_THRESHOLD = float(os.environ.get("JAC_AMOUNT_THRESHOLD", "5000.0"));

        if here.amount > AMOUNT_THRESHOLD {
            here.flagged = true;
            self.suspicious_txs += 1;
        }

        # Propagate flag from a flagged sender
        senders = [<-:Sends:<-][?:Account];
        for sender in senders {
            if sender.flagged and not here.flagged {
                here.flagged = true;
                self.suspicious_txs += 1;
            }
        }

        report here;
        visit [->:Receives:->];
    }
}

def setup_graph() -> list[str] {
    NUM_ACCOUNTS = int(os.environ.get("JAC_NUM_ACCOUNTS", "200"));
    TXS_PER_ACCOUNT = int(os.environ.get("JAC_TXS_PER_ACCOUNT", "8"));
    SEED = int(os.environ.get("JAC_SEED", "42"));

    random.seed(SEED);

    accounts: dict[int, Account] = {};

    # Create Account nodes
    for i in range(NUM_ACCOUNTS) {
        bal = round(random.uniform(100.0, 50000.0), 2);
        a = Account(id=i, balance=bal);
        accounts[i] = a;
        root ++> a;
    }

    print(f"Created {NUM_ACCOUNTS} accounts");

    # Create Transaction nodes and connect them
    tx_counter = 0;
    for (acct_id, acct) in accounts.items() {
        n_txs = random.randint(1, TXS_PER_ACCOUNT * 2);   # variable velocity
        acct.tx_count = n_txs;
        for _ in range(n_txs) {
            amt = round(random.uniform(1.0, 10000.0), 2);
            tx = Transaction(id=tx_counter, amount=amt);
            tx_counter += 1;

            # sender -> tx -> random receiver account
            receiver_id = random.randint(0, NUM_ACCOUNTS - 1);
            receiver = accounts[receiver_id];

            acct +>: Sends :+> tx;
            tx   +>: Receives :+> receiver;
        }
    }

    print(f"Created {tx_counter} transactions");
    print(f"root: {root.__jac__.id}");

    return [str(a.__jac__.id) for a in accounts.values()];
}
