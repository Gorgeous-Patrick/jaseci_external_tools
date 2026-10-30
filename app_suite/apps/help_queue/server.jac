"""HelpQueue: customer tickets, agent assignment and deterministic SLA escalation."""

import from typing { cast }

node SupportDesk {
    has name: str,
        tick: int;
}
node Customer {
    has name: str;
}
node Agent {
    has name: str,
        tier: int;
}
node SLA {
    has priority: str,
        response_minutes: int;
}
node Ticket {
    has subject: str,
        priority: str,
        opened_tick: int,
        status: str = "open",
        escalated: bool = False;
}
node Reply {
    has body: str,
        tick: int;
}
edge HasCustomer {}
edge HasAgent {}
edge HasSLA {}
edge HasTicket {}
edge OpenedBy {}
edge AssignedAgent {}
edge UsesSLA {}
edge HasReply {}

def _desk -> SupportDesk | None {
    desks = [root-->[?:SupportDesk]];
    return desks[0] if desks else None;
}

def _owned_ticket(ticket: object) -> bool {
    desk = _desk();
    return desk is not None
        and isinstance(ticket, Ticket)
        and jid(ticket) in [jid(item) for item in [desk->:HasTicket:->[?:Ticket]]];
}

def _escalate(ticket: Ticket) -> None {
    desk = cast(SupportDesk, _desk());
    senior = [desk->:HasAgent:->[?:Agent, tier==2]][0];
    for edge in [edge ticket->:AssignedAgent:->] {
        del edge;
    }
    ticket +>:AssignedAgent:+> senior;
    ticket.escalated = True;
}

def _ticket_view(ticket: Ticket) -> dict {
    customer = [ticket->:OpenedBy:->[?:Customer]][0];
    agents = [ticket->:AssignedAgent:->[?:Agent]];
    sla = [ticket->:UsesSLA:->[?:SLA]][0];
    return {
        "id": jid(ticket),
        "subject": ticket.subject,
        "priority": ticket.priority,
        "opened_tick": ticket.opened_tick,
        "status": ticket.status,
        "escalated": ticket.escalated,
        "customer": customer.name,
        "response_minutes": sla.response_minutes,
        "agents": [
            {"id": jid(agent), "name": agent.name, "tier": agent.tier}
            for agent in agents
        ],
        "replies": [
            {"id": jid(reply), "body": reply.body, "tick": reply.tick}
            for reply in [ticket->:HasReply:->[?:Reply]]
        ]
    };
}

walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:SupportDesk]] {
            report {"ok": True, "created": False};
            return;
        }
        desk = here ++> SupportDesk(
            name="Research Help Desk", tick=1000 + self.seed % 3
        );
        north = desk +>:HasCustomer:+> Customer(name="North Lab");
        desk +>:HasCustomer:+> Customer(name="South Lab");
        desk +>:HasAgent:+> Agent(name="Riley", tier=1);
        desk +>:HasAgent:+> Agent(name="Sam", tier=2);
        urgent = desk +>:HasSLA:+> SLA(priority="urgent", response_minutes=30);
        desk +>:HasSLA:+> SLA(priority="normal", response_minutes=120);
        ticket = desk +>:HasTicket:+> Ticket(
            subject="Sensor offline", priority="urgent", opened_tick=desk.tick
        );
        ticket +>:OpenedBy:+> north;
        ticket +>:UsesSLA:+> urgent;
        report {"ok": True, "created": True};
    }
}

walker DeskBoard {
    has desks: list[dict] = [],
        customers: list[dict] = [],
        agents: list[dict] = [],
        tickets: list[dict] = [];

    can start with Root entry {
        visit [-->[?:SupportDesk]];
    }
    can desk with SupportDesk entry {
        self.desks.append({"id": jid(here), "name": here.name, "tick": here.tick});
        visit [->:HasCustomer:->[?:Customer]];
        visit [->:HasAgent:->[?:Agent]];
        visit [->:HasTicket:->[?:Ticket]];
    }

    can customer with Customer entry {
        self.customers.append({"id": jid(here), "name": here.name});
    }
    can agent with Agent entry {
        self.agents.append({"id": jid(here), "name": here.name, "tier": here.tier});
    }
    can ticket with Ticket entry {
        self.tickets.append(_ticket_view(here));
    }
    can finish with Root exit {
        report {
            "desks": self.desks,
            "customers": self.customers,
            "agents": self.agents,
            "tickets": self.tickets
        };
    }
}

walker CreateTicket {
    has subject: str,
        customer_id: str,
        priority: str;

    can create with Root entry {
        desk = _desk();
        customer = jobj(self.customer_id);
        if desk is None
            or not isinstance(customer, Customer)
            or self.customer_id
                not in [jid(item) for item in [desk->:HasCustomer:->[?:Customer]]] {
            report {"ok": False, "error": "Customer is not available to this user"};
            return;
        }
        if not self.subject.strip() or self.priority not in ["urgent", "normal"] {
            report {
                "ok": False,
                "error": "Enter a subject and select urgent or normal priority"
            };
            return;
        }
        sla = [
            item
            for item in [desk->:HasSLA:->[?:SLA]]
            if item.priority == self.priority
        ][0];
        ticket = desk +>:HasTicket:+> Ticket(
            subject=self.subject.strip(), priority=self.priority, opened_tick=desk.tick
        );
        ticket +>:OpenedBy:+> customer;
        ticket +>:UsesSLA:+> sla;
        report {"ok": True, "ticket": _ticket_view(ticket)};
    }
}

walker AssignTicket {
    has ticket_id: str,
        agent_id: str;

    can assign with Root entry {
        ticket = jobj(self.ticket_id);
        agent = jobj(self.agent_id);
        desk = _desk();
        if desk is None
            or not _owned_ticket(ticket)
            or not isinstance(agent, Agent)
            or self.agent_id
                not in [jid(item) for item in [desk->:HasAgent:->[?:Agent]]] {
            report {"ok": False, "error": "Select an available ticket and agent"};
            return;
        }
        ticket = cast(Ticket, ticket);
        if ticket.status != "open" or (ticket.escalated and agent.tier < 2) {
            report {
                "ok": False,
                "error": "Open escalated tickets require a senior agent"
            };
            return;
        }
        for edge in [edge ticket->:AssignedAgent:->] {
            del edge;
        }
        ticket +>:AssignedAgent:+> agent;
        report {"ok": True, "ticket": _ticket_view(ticket)};
    }
}

walker AdvanceClock {
    has minutes: int;

    can advance with Root entry {
        desk = _desk();
        if desk is None or self.minutes < 0 {
            report {"ok": False, "error": "Clock advance must be nonnegative"};
            return;
        }
        desk.tick += self.minutes;
        report {"ok": True, "tick": desk.tick};
    }
}

walker EvaluateSLA {
    has now: int = 0,
        escalated_ids: list[str] = [];

    can start with Root entry {
        visit [-->[?:SupportDesk]];
    }
    can clock with SupportDesk entry {
        self.now = here.tick;
        visit [->:HasTicket:->[?:Ticket]];
    }
    can ticket with Ticket entry {
        if here.status == "open" and not [here->:HasReply:->[?:Reply]] {
            sla = [here->:UsesSLA:->[?:SLA]][0];
            if self.now - here.opened_tick >= sla.response_minutes {
                _escalate(here);
                self.escalated_ids.append(jid(here));
            }
        }
    }

    can finish with Root exit {
        report {"ok": True, "escalated_ids": self.escalated_ids};
    }
}

walker ReplyTicket {
    has ticket_id: str,
        body: str;

    can reply with Root entry {
        ticket = jobj(self.ticket_id);
        desk = _desk();
        if desk is None or not _owned_ticket(ticket) or not self.body.strip() {
            report {
                "ok": False,
                "error": "Select an available ticket and enter a reply"
            };
            return;
        }
        ticket = cast(Ticket, ticket);
        if ticket.status != "open" {
            report {"ok": False, "error": "Resolved tickets cannot receive replies"};
            return;
        }
        if not [ticket->:HasReply:->[?:Reply]] {
            sla = [ticket->:UsesSLA:->[?:SLA]][0];
            if desk.tick - ticket.opened_tick >= sla.response_minutes {
                _escalate(ticket);
            }
        }
        ticket +>:HasReply:+> Reply(body=self.body.strip(), tick=desk.tick);
        report {"ok": True, "ticket": _ticket_view(ticket)};
    }
}

walker ResolveTicket {
    has ticket_id: str;

    can resolve with Root entry {
        ticket = jobj(self.ticket_id);
        if not _owned_ticket(ticket) {
            report {"ok": False, "error": "Ticket is not available to this user"};
            return;
        }
        ticket = cast(Ticket, ticket);
        if ticket.status != "open" or not [ticket->:HasReply:->[?:Reply]] {
            report {
                "ok": False,
                "error": "Only open tickets with a reply can be resolved"
            };
            return;
        }
        ticket.status = "resolved";
        report {"ok": True, "ticket": _ticket_view(ticket)};
    }
}
