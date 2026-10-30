"""Versioned articles, review-bound publication and cycle-safe backlink exploration."""
import from typing { cast }
node Article {
    has title: str,
        published_revision: int = 0;
}
node Revision {
    has number: int,
        body: str,
        reviewed: bool = False;
}
node Review {
    has note: str;
}
node Topic {
    has name: str;
}
edge HasRevision {}
edge HasReview {}
edge Tagged {}
edge LinksTo {}
def _article(a: object) -> bool {
    return isinstance(a, Article) and jid(a) in [jid(x) for x in [root-->[?:Article]]];
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Article]] {
            report {"ok": True};
            return;
        }
        topic = Topic(name="Graph systems");
        for title in ["Storage notes", "Traversal guide", "Release handbook"] {
            a = here ++> Article(title=title);
            a +>:Tagged:+> topic;
            a +>:HasRevision:+> Revision(
                number=1, body="Research draft " + str(self.seed)
            );
        }
        report {"ok": True};
    }
}

walker KnowledgeBoard {
    has articles: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Article]];
    }
    can article with Article entry {
        self.articles.append(
            {
                "id": jid(here),
                "title": here.title,
                "published_revision": here.published_revision,
                "topics": [t.name for t in [here->:Tagged:->[?:Topic]]],
                "links": [jid(a) for a in [here->:LinksTo:->[?:Article]]],
                "backlinks": [a.title for a in [here<-:LinksTo:<-[?:Article]]],
                "revisions": [
                    {
                        "id": jid(r),
                        "number": r.number,
                        "body": r.body,
                        "reviewed": r.reviewed
                    } for r in [here->:HasRevision:->[?:Revision]]
                ]
            }
        );
    }
    can finish with Root exit {
        report {"articles": self.articles};
    }
}

walker ReviseArticle {
    has article_id: str,
        body: str;

    can revise with Root entry {
        a = jobj(self.article_id);
        if not _article(a) or not self.body.strip() {
            report {"ok": False, "error": "Select an article and enter revision text"};
            return;
        }
        a = cast(Article, a);
        r = a +>:HasRevision:+> Revision(
            number=len([a->:HasRevision:->[?:Revision]]) + 1, body=self.body.strip()
        );
        report {"ok": True, "revision_id": jid(r)};
    }
}

walker ReviewRevision {
    has revision_id: str,
        note: str;

    can review with Root entry {
        r = jobj(self.revision_id);
        if not isinstance(r, Revision)
            or not any(_article(a) for a in [r<-:HasRevision:<-[?:Article]])
            or not self.note.strip() {
            report {"ok": False, "error": "Select a revision and enter a review note"};
            return;
        }
        if r.reviewed {
            report {"ok": False, "error": "Revision has already been reviewed"};
            return;
        }
        r +>:HasReview:+> Review(note=self.note.strip());
        r.reviewed = True;
        report {"ok": True};
    }
}

walker PublishArticle {
    has article_id: str;

    can publish with Root entry {
        a = jobj(self.article_id);
        if not _article(a) {
            report {"ok": False, "error": "Article is not available"};
            return;
        }
        a = cast(Article, a);
        latest = [a->:HasRevision:->[?:Revision]][-1];
        if not latest.reviewed or a.published_revision == latest.number {
            report {
                "ok": False,
                "error": "Review the latest unpublished revision before publication"
            };
            return;
        }
        a.published_revision = latest.number;
        report {"ok": True};
    }
}

walker LinkArticles {
    has source_id: str,
        target_id: str;

    can link with Root entry {
        a = jobj(self.source_id);
        b = jobj(self.target_id);
        if not _article(a) or not _article(b) or self.source_id == self.target_id {
            report {"ok": False, "error": "Select two different owned articles"};
            return;
        }
        a = cast(Article, a);
        b = cast(Article, b);
        if self.target_id not in [jid(x) for x in [a->:LinksTo:->[?:Article]]] {
            a +>:LinksTo:+> b;
        }
        report {"ok": True};
    }
}

walker ExploreLinks {
    has article_id: str,
        seen: set[str] = set(),
        titles: list[str] = [];

    can start with Root entry {
        a = jobj(self.article_id);
        if _article(a) {
            visit [a];
        }
    }
    can article with Article entry {
        if jid(here) in self.seen {
            return;
        }
        self.seen.add(jid(here));
        self.titles.append(here.title);
        visit [->:LinksTo:->[?:Article]];
    }
    can finish with Root exit {
        report self.titles;
    }
}
