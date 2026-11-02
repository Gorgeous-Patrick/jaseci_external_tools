"""SNB Interactive v1 graph research adapter with full results for all 29 operations.

Includes independent fixture/oracle contracts and explicit edition deviations
in SEMANTICS.md; native acceptance is evidence-backed in the suite inventory.
"""
import from typing { cast }
import from fixture_loader { seed_graph, friendship_dates, edge_rows }
node Person {
    has person_id: int, first_name: str, last_name: str, birthday: str,
        location_ip: str, browser: str, gender: str, creation_date: int, emails: list[str] = [], languages: list[str] = [];
}
node Place { has place_id: int, name: str, kind: str = "City"; }
node Forum { has forum_id: int, title: str, creation_date: int = 0; }
node Message {
    has message_id: int, content: str, image_file: str, creation_date: int,
        is_comment: bool = False, length: int = 0, language: str = "", location_ip: str = "", browser: str = "";
}
edge Knows { has creation_date: int; }
edge LocatedIn {}
edge HasCreator {}
edge ReplyOf {}
edge ContainerOf {}
edge HasModerator {}
node Organization { has organization_id: int, name: str, kind: str; }
node Tag { has tag_id: int, name: str; }
node TagClass { has class_id: int, name: str; }
edge PartOf {}
edge HasType {}
edge SubClassOf {}
edge Interest {}
edge HasTag {}
edge StudyAt { has year: int; }
edge WorkAt { has year: int; }
edge HasMember { has join_date: int; }
edge Likes { has creation_date: int; }
walker Seed {
    has directory: str;
    can seed with Root entry {
        if [-->] { report {"ok": False, "error": "Fixture root is not empty"}; return; }
        report seed_graph(self.directory,
            {"Person": Person, "Place": Place, "Forum": Forum, "Message": Message, "Organization": Organization, "Tag": Tag, "TagClass": TagClass},
            {"Knows": Knows, "LocatedIn": LocatedIn, "HasCreator": HasCreator,
             "ReplyOf": ReplyOf, "ContainerOf": ContainerOf, "HasModerator": HasModerator, "PartOf": PartOf, "HasType": HasType, "SubClassOf": SubClassOf, "Interest": Interest, "HasTag": HasTag, "StudyAt": StudyAt, "WorkAt": WorkAt, "HasMember": HasMember, "Likes": Likes});
    }
}
walker IS1 {
    has person_jid: str, rows: list[dict] = [];
    can start with Root entry { visit [cast(Person, jobj(self.person_jid))]; }
    can profile with Person entry {
        cities = [here->:LocatedIn:->[?:Place]];
        self.rows.append({"firstName": here.first_name, "lastName": here.last_name,
            "birthday": here.birthday, "locationIP": here.location_ip,
            "browserUsed": here.browser, "cityId": cities[0].place_id,
            "gender": here.gender, "creationDate": here.creation_date});
    }
    can finish with Root exit { report self.rows; }
}
walker _OriginalPost {
    has original_id: int = -1, creator: dict = {};
    can message with Message entry {
        if here.is_comment { visit [->:ReplyOf:->[?:Message]]; }
        else {
            self.original_id = here.message_id;
            visit [->:HasCreator:->[?:Person]];
        }
    }
    can author with Person entry {
        self.creator = {"personId": here.person_id, "firstName": here.first_name,
            "lastName": here.last_name};
    }
}
def _content(m: Message) -> str { return m.image_file if m.image_file else m.content; }
walker IS2 {
    has person_jid: str, messages: list[Message] = [];
    can start with Root entry { visit [cast(Person, jobj(self.person_jid))]; }
    can person with Person entry { visit [<-:HasCreator:<-[?:Message]]; }
    can message with Message entry { self.messages.append(here); }
    can finish with Root exit {
        self.messages.sort(key=lambda (m: Message) { (-m.creation_date, -m.message_id); });
        rows: list[dict] = [];
        for message in self.messages[:10] {
            original = _OriginalPost();
            message spawn original;
            rows.append({"messageId": message.message_id, "messageContent": _content(message),
                "messageCreationDate": message.creation_date, "originalPostId": original.original_id,
                "originalPostAuthorId": original.creator["personId"],
                "originalPostAuthorFirstName": original.creator["firstName"],
                "originalPostAuthorLastName": original.creator["lastName"]});
        }
        report rows;
    }
}
walker IS3 {
    has person_jid: str, dates: dict = {}, rows: list[dict] = [];
    can start with Root entry {
        p = cast(Person, jobj(self.person_jid));
        self.dates = friendship_dates(p);
        visit [p->:Knows:->[?:Person]] + [p<-:Knows:<-[?:Person]];
    }
    can friend with Person entry {
        self.rows.append({"personId": here.person_id, "firstName": here.first_name,
            "lastName": here.last_name, "friendshipCreationDate": self.dates[jid(here)]});
    }
    can finish with Root exit {
        self.rows.sort(key=lambda (row: dict) { (-row["friendshipCreationDate"], row["personId"]); });
        report self.rows;
    }
}
walker IS4 {
    has message_jid: str, rows: list[dict] = [];
    can start with Root entry { visit [cast(Message, jobj(self.message_jid))]; }
    can message with Message entry { self.rows.append({"messageContent": _content(here), "messageCreationDate": here.creation_date}); }
    can finish with Root exit { report self.rows; }
}
walker IS5 {
    has message_jid: str, rows: list[dict] = [];
    can start with Root entry { visit [cast(Message, jobj(self.message_jid))]; }
    can message with Message entry { visit [->:HasCreator:->[?:Person]]; }
    can author with Person entry { self.rows.append({"personId": here.person_id, "firstName": here.first_name, "lastName": here.last_name}); }
    can finish with Root exit { report self.rows; }
}
walker IS6 {
    has message_jid: str, forum_id: int = -1, title: str = "", rows: list[dict] = [];
    can start with Root entry { visit [cast(Message, jobj(self.message_jid))]; }
    can message with Message entry {
        if here.is_comment { visit [->:ReplyOf:->[?:Message]]; }
        else { visit [<-:ContainerOf:<-[?:Forum]]; }
    }
    can forum with Forum entry {
        self.forum_id = here.forum_id; self.title = here.title;
        visit [->:HasModerator:->[?:Person]];
    }
    can moderator with Person entry { self.rows.append({"forumId": self.forum_id, "forumTitle": self.title,
        "moderatorId": here.person_id, "moderatorFirstName": here.first_name, "moderatorLastName": here.last_name}); }
    can finish with Root exit { report self.rows; }
}
walker IS7 {
    has message_jid: str, author_jid: str = "", rows: list[dict] = [];
    can start with Root entry {
        m = cast(Message, jobj(self.message_jid));
        self.author_jid = jid([m->:HasCreator:->[?:Person]][0]);
        visit [m<-:ReplyOf:<-[?:Message]];
    }
    can reply with Message entry {
        p = [here->:HasCreator:->[?:Person]][0];
        neighbors = [p->:Knows:->[?:Person]] + [p<-:Knows:<-[?:Person]];
        self.rows.append({"commentId": here.message_id, "commentContent": here.content,
            "commentCreationDate": here.creation_date, "replyAuthorId": p.person_id,
            "replyAuthorFirstName": p.first_name, "replyAuthorLastName": p.last_name,
            "replyAuthorKnowsOriginalMessageAuthor": self.author_jid in [jid(x) for x in neighbors]});
    }
    can finish with Root exit {
        self.rows.sort(key=lambda (row: dict) { (-row["commentCreationDate"], row["replyAuthorId"]); });
        report self.rows;
    }
}
walker IC13 {
    has person1_jid: str, person2_jid: str;
    can run with Root entry {
        start = cast(Person, jobj(self.person1_jid));
        target = cast(Person, jobj(self.person2_jid));
        frontier: list[Person] = [start];
        seen: dict = {jid(start): True}; distance = 0;
        while frontier {
            if jid(target) in [jid(x) for x in frontier] { report {"shortestPathLength": distance}; return; }
            next_frontier: list[Person] = [];
            for person in frontier {
                for neighbor in [person->:Knows:->[?:Person]] + [person<-:Knows:<-[?:Person]] {
                    if jid(neighbor) not in seen { seen[jid(neighbor)] = True; next_frontier.append(neighbor); }
                }
            }
            frontier = next_frontier; distance += 1;
        }
        report {"shortestPathLength": -1};
    }
}

# The following helpers preserve the procedural graph representation, not a
# rewritten query algorithm chosen for a particular prefetch policy.
def _friends(p: Person) -> list[Person] {
    return [p->:Knows:->[?:Person]] + [p<-:Knows:<-[?:Person]];
}
def _near(p: Person, depth: int) -> dict {
    found: dict = {}; seen: dict = {jid(p): True}; frontier: list[Person] = [p];
    for distance in range(1, depth + 1) {
        next_frontier: list[Person] = [];
        for current in frontier {
            for person in _friends(current) {
                if jid(person) not in seen {
                    seen[jid(person)] = True; found[jid(person)] = {"person": person, "distance": distance};
                    next_frontier.append(person);
                }
            }
        }
        frontier = next_frontier;
    }
    return found;
}
def _author(message: Message) -> Person { return [message->:HasCreator:->[?:Person]][0]; }
def _tags(message: Message) -> list[Tag] { return [message->:HasTag:->[?:Tag]]; }
walker IC1 {
    has person_jid: str, first_name: str, distances: dict = {}, rows: list[dict] = [];
    can start with Root entry {
        candidates = _near(cast(Person, jobj(self.person_jid)), 3);
        self.distances = {key: item["distance"] for (key, item) in candidates.items()};
        visit [cast(Person, item["person"]) for item in candidates.values()];
    }
    can person with Person entry {
        if here.first_name != self.first_name { return; }
        city = [here->:LocatedIn:->[?:Place]][0];
        universities: list[list] = []; companies: list[list] = [];
        for work in edge_rows(here, "StudyAt") {
            organization = cast(Organization, work["target"]);
            universities.append([organization.name, work["year"], [organization->:LocatedIn:->[?:Place]][0].name]);
        }
        for work in edge_rows(here, "WorkAt") {
            organization = cast(Organization, work["target"]);
            companies.append([organization.name, work["year"], [organization->:LocatedIn:->[?:Place]][0].name]);
        }
        self.rows.append({"friendId": here.person_id, "friendLastName": here.last_name,
            "distanceFromPerson": self.distances[jid(here)], "friendBirthday": here.birthday,
            "friendCreationDate": here.creation_date, "friendGender": here.gender,
            "friendBrowserUsed": here.browser, "friendLocationIp": here.location_ip,
            "friendEmails": here.emails, "friendLanguages": here.languages,
            "friendCityName": city.name, "friendUniversities": universities, "friendCompanies": companies});
    }
    can finish with Root exit {
        self.rows.sort(key=lambda (r: dict) { (r["distanceFromPerson"], r["friendLastName"], r["friendId"]); });
        report self.rows[:20];
    }
}
walker IC2 {
    has person_jid: str, max_date: int, rows: list[dict] = [];
    can start with Root entry { visit _friends(cast(Person, jobj(self.person_jid))); }
    can person with Person entry { visit [<-:HasCreator:<-[?:Message]]; }
    can message with Message entry {
        if here.creation_date < self.max_date {
            person = _author(here);
            self.rows.append({"personId": person.person_id, "personFirstName": person.first_name,
                "personLastName": person.last_name, "messageId": here.message_id,
                "messageContent": _content(here), "messageCreationDate": here.creation_date});
        }
    }
    can finish with Root exit {
        self.rows.sort(key=lambda (r: dict) { (-r["messageCreationDate"], r["messageId"]); }); report self.rows[:20];
    }
}
walker IC3 {
    has person_jid: str, country_x: str, country_y: str, start_date: int, duration_days: int,
        counts: dict = {}, people: dict = {};
    can start with Root entry { visit [cast(Person, v["person"]) for v in _near(cast(Person, jobj(self.person_jid)), 2).values()]; }
    can person with Person entry {
        city = [here->:LocatedIn:->[?:Place]][0]; country = [city->:PartOf:->[?:Place]][0];
        if country.name not in [self.country_x, self.country_y] {
            self.people[str(here.person_id)] = here; self.counts[str(here.person_id)] = [0, 0];
            visit [<-:HasCreator:<-[?:Message]];
        }
    }
    can message with Message entry {
        if self.start_date <= here.creation_date < self.start_date + self.duration_days * 86400000 {
            location = [here->:LocatedIn:->[?:Place]][0]; key = str(_author(here).person_id);
            if location.name == self.country_x { self.counts[key][0] += 1; }
            if location.name == self.country_y { self.counts[key][1] += 1; }
        }
    }
    can finish with Root exit {
        rows: list[dict] = [];
        for (key, counts) in self.counts.items() {
            if counts[0] > 0 and counts[1] > 0 {
                person = cast(Person, self.people[key]);
                rows.append({"personId": person.person_id, "personFirstName": person.first_name,
                    "personLastName": person.last_name, "xCount": counts[0], "yCount": counts[1], "count": counts[0] + counts[1]});
            }
        }
        rows.sort(key=lambda (r: dict) { (-r["count"], r["personId"]); }); report rows[:20];
    }
}
walker IC4 {
    has person_jid: str, start_date: int, duration_days: int, old: dict = {}, counts: dict = {};
    can start with Root entry { visit _friends(cast(Person, jobj(self.person_jid))); }
    can person with Person entry { visit [<-:HasCreator:<-[?:Message, is_comment == False]]; }
    can message with Message entry {
        for tag in _tags(here) {
            if here.creation_date < self.start_date { self.old[tag.name] = True; }
            elif here.creation_date < self.start_date + self.duration_days * 86400000 { self.counts[tag.name] = self.counts.get(tag.name, 0) + 1; }
        }
    }
    can finish with Root exit {
        rows = [{"tagName": name, "postCount": count} for (name, count) in self.counts.items() if name not in self.old];
        rows.sort(key=lambda (r: dict) { (-r["postCount"], r["tagName"]); }); report rows[:10];
    }
}
walker IC5 {
    has person_jid: str, min_date: int;
    can run with Root entry {
        persons = _near(cast(Person, jobj(self.person_jid)), 2); forums: dict = {};
        for item in persons.values() {
            person = cast(Person, item["person"]);
            for membership in edge_rows(person, "HasMember", False) {
                if membership["join_date"] > self.min_date {
                    forum = cast(Forum, membership["source"]); key = str(forum.forum_id);
                    if key not in forums { forums[key] = {"forumId": forum.forum_id, "forumTitle": forum.title, "postCount": 0}; }
                    forums[key]["postCount"] += len([m for m in [forum->:ContainerOf:->[?:Message]] if _author(m).person_id == person.person_id]);
                }
            }
        }
        rows = list(forums.values()); rows.sort(key=lambda (r: dict) { (-r["postCount"], r["forumId"]); });
        report [{"forumTitle": r["forumTitle"], "postCount": r["postCount"]} for r in rows[:20]];
    }
}
walker IC6 {
    has person_jid: str, tag_name: str, counts: dict = {};
    can start with Root entry { visit [cast(Person, v["person"]) for v in _near(cast(Person, jobj(self.person_jid)), 2).values()]; }
    can person with Person entry { visit [<-:HasCreator:<-[?:Message, is_comment == False]]; }
    can message with Message entry {
        tags = _tags(here);
        if self.tag_name in [tag.name for tag in tags] {
            for tag in tags { if tag.name != self.tag_name { self.counts[tag.name] = self.counts.get(tag.name, 0) + 1; } }
        }
    }
    can finish with Root exit {
        rows = [{"tagName": name, "postCount": count} for (name, count) in self.counts.items()];
        rows.sort(key=lambda (r: dict) { (-r["postCount"], r["tagName"]); }); report rows[:10];
    }
}
walker IC7 {
    has person_jid: str;
    can run with Root entry {
        person = cast(Person, jobj(self.person_jid)); latest: dict = {};
        for message in [person<-:HasCreator:<-[?:Message]] {
            for like in edge_rows(message, "Likes", False) {
                liker = cast(Person, like["source"]); key = str(liker.person_id);
                row = {"personId": liker.person_id, "personFirstName": liker.first_name,
                    "personLastName": liker.last_name, "likeCreationDate": like["creation_date"],
                    "commentOrPostId": message.message_id, "commentOrPostContent": _content(message),
                    "minutesLatency": (like["creation_date"] - message.creation_date) // 60000,
                    "isNew": liker.person_id not in [p.person_id for p in _friends(person)]};
                if key not in latest or row["likeCreationDate"] > latest[key]["likeCreationDate"] or (row["likeCreationDate"] == latest[key]["likeCreationDate"] and row["commentOrPostId"] < latest[key]["commentOrPostId"]) { latest[key] = row; }
            }
        }
        rows = list(latest.values()); rows.sort(key=lambda (r: dict) { (-r["likeCreationDate"], r["personId"]); }); report rows[:20];
    }
}
walker IC8 {
    has person_jid: str, rows: list[dict] = [];
    can start with Root entry {
        person = cast(Person, jobj(self.person_jid));
        for message in [person<-:HasCreator:<-[?:Message]] { visit [message<-:ReplyOf:<-[?:Message]]; }
    }
    can message with Message entry {
        person = _author(here);
        self.rows.append({"personId": person.person_id, "personFirstName": person.first_name,
            "personLastName": person.last_name, "commentCreationDate": here.creation_date,
            "commentId": here.message_id, "commentContent": here.content});
    }
    can finish with Root exit { self.rows.sort(key=lambda (r: dict) { (-r["commentCreationDate"], r["commentId"]); }); report self.rows[:20]; }
}
walker IC9 {
    has person_jid: str, max_date: int, rows: list[dict] = [];
    can start with Root entry { visit [cast(Person, v["person"]) for v in _near(cast(Person, jobj(self.person_jid)), 2).values()]; }
    can person with Person entry { visit [<-:HasCreator:<-[?:Message]]; }
    can message with Message entry {
        if here.creation_date < self.max_date {
            person = _author(here);
            self.rows.append({"personId": person.person_id, "personFirstName": person.first_name,
                "personLastName": person.last_name, "messageId": here.message_id,
                "messageContent": _content(here), "messageCreationDate": here.creation_date});
        }
    }
    can finish with Root exit { self.rows.sort(key=lambda (r: dict) { (-r["messageCreationDate"], r["messageId"]); }); report self.rows[:20]; }
}
walker IC10 {
    has person_jid: str, month: int, rows: list[dict] = [];
    can start with Root entry {
        person = cast(Person, jobj(self.person_jid)); direct = [p.person_id for p in _friends(person)];
        visit [cast(Person, v["person"]) for v in _near(person, 2).values() if cast(Person, v["person"]).person_id not in direct];
    }
    can person with Person entry {
        month = int(here.birthday[5:7]); day = int(here.birthday[8:10]);
        if not ((month == self.month and day >= 21) or (month == self.month % 12 + 1 and day < 22)) { return; }
        start = cast(Person, jobj(self.person_jid)); interests = [t.tag_id for t in [start->:Interest:->[?:Tag]]];
        score = 0;
        for post in [here<-:HasCreator:<-[?:Message, is_comment == False]] {
            score += 1 if any(t.tag_id in interests for t in _tags(post)) else -1;
        }
        self.rows.append({"personId": here.person_id, "personFirstName": here.first_name,
            "personLastName": here.last_name, "commonInterestScore": score,
            "personGender": here.gender, "personCityName": [here->:LocatedIn:->[?:Place]][0].name});
    }
    can finish with Root exit { self.rows.sort(key=lambda (r: dict) { (-r["commonInterestScore"], r["personId"]); }); report self.rows[:10]; }
}
walker IC11 {
    has person_jid: str, country_name: str, work_from_year: int, rows: list[dict] = [];
    can start with Root entry { visit [cast(Person, v["person"]) for v in _near(cast(Person, jobj(self.person_jid)), 2).values()]; }
    can person with Person entry {
        for work in edge_rows(here, "WorkAt") {
            organization = cast(Organization, work["target"]); country = [organization->:LocatedIn:->[?:Place]][0];
            if country.name == self.country_name and work["year"] < self.work_from_year {
                self.rows.append({"personId": here.person_id, "personFirstName": here.first_name,
                    "personLastName": here.last_name, "organizationName": organization.name,
                    "organizationWorkFromYear": work["year"]});
            }
        }
    }
    can finish with Root exit {
        self.rows.sort(key=lambda (r: dict) { r["organizationName"]; }, reverse=True);
        self.rows.sort(key=lambda (r: dict) { (r["organizationWorkFromYear"], r["personId"]); }); report self.rows[:10];
    }
}
def _is_class(tag: Tag, name: str) -> bool {
    pending = [tag->:HasType:->[?:TagClass]]; seen: dict = {};
    while pending {
        current = pending.pop();
        if jid(current) in seen { continue; }
        seen[jid(current)] = True;
        if current.name == name { return True; }
        pending.extend([current->:SubClassOf:->[?:TagClass]]);
    }
    return False;
}
walker IC12 {
    has person_jid: str, tag_class_name: str, rows: list[dict] = [];
    can start with Root entry { visit _friends(cast(Person, jobj(self.person_jid))); }
    can person with Person entry {
        names: dict = {}; comments: dict = {};
        for comment in [here<-:HasCreator:<-[?:Message, is_comment == True]] {
            posts = [comment->:ReplyOf:->[?:Message, is_comment == False]];
            for post in posts {
                for tag in _tags(post) {
                    if _is_class(tag, self.tag_class_name) { names[tag.name] = True; comments[str(comment.message_id)] = True; }
                }
            }
        }
        if comments {
            self.rows.append({"personId": here.person_id, "personFirstName": here.first_name,
                "personLastName": here.last_name, "tagNames": sorted(names.keys()), "replyCount": len(comments)});
        }
    }
    can finish with Root exit { self.rows.sort(key=lambda (r: dict) { (-r["replyCount"], r["personId"]); }); report self.rows[:20]; }
}
def _edge_weight(a: Person, b: Person) -> float {
    weight = 0.0;
    for pair in [[a, b], [b, a]] {
        for comment in [pair[0]<-:HasCreator:<-[?:Message, is_comment == True]] {
            for parent in [comment->:ReplyOf:->[?:Message]] {
                if _author(parent).person_id == pair[1].person_id { weight += 0.5 if parent.is_comment else 1.0; }
            }
        }
    }
    return weight;
}
walker IC14 {
    has person1_jid: str, person2_jid: str;
    can run with Root entry {
        start = cast(Person, jobj(self.person1_jid)); target = cast(Person, jobj(self.person2_jid));
        frontier: list[list[Person]] = [[start]]; solutions: list[list[Person]] = [];
        while frontier and not solutions {
            next_frontier: list[list[Person]] = [];
            for path in frontier {
                if path[-1].person_id == target.person_id { solutions.append(path); }
                else {
                    for friend in _friends(path[-1]) {
                        if friend.person_id not in [p.person_id for p in path] { next_frontier.append(path + [friend]); }
                    }
                }
            }
            frontier = next_frontier;
        }
        rows: list[dict] = [];
        for path in solutions {
            weight = 0.0;
            for i in range(len(path) - 1) { weight += _edge_weight(path[i], path[i + 1]); }
            rows.append({"personIdsInPath": [p.person_id for p in path], "pathWeight": weight});
        }
        rows.sort(key=lambda (r: dict) { -r["pathWeight"]; }); report rows;
    }
}

walker U1 {
    has person_id: int, first_name: str, last_name: str, birthday: str,
        location_ip: str, browser: str, gender: str, creation_date: int,
        city_jid: str, emails: list[str], languages: list[str],
        tag_jids: list[str], study_at: list[dict], work_at: list[dict];
    can run with Root entry {
        if [-->[?:Person, person_id == self.person_id]] { raise ValueError("Duplicate person"); }
        person = here ++> Person(person_id=self.person_id, first_name=self.first_name,
            last_name=self.last_name, birthday=self.birthday, location_ip=self.location_ip,
            browser=self.browser, gender=self.gender, creation_date=self.creation_date,
            emails=self.emails, languages=self.languages);
        person +>:LocatedIn:+> cast(Place, jobj(self.city_jid));
        # Check duplicate component keys after the Person write, so native abort
        # must roll back earlier changes rather than relying on validate-first.
        if len(set(self.emails)) != len(self.emails) or len(set(self.languages)) != len(self.languages) { raise ValueError("Duplicate person component"); }
        for key in self.tag_jids { person +>:Interest:+> cast(Tag, jobj(key)); }
        for item in self.study_at { person +>:StudyAt(year=item["year"]):+> cast(Organization, jobj(item["organization_jid"])); }
        for item in self.work_at { person +>:WorkAt(year=item["year"]):+> cast(Organization, jobj(item["organization_jid"])); }
        report None;
    }
}
walker U2 {
    has person_jid: str, message_jid: str, creation_date: int;
    can run with Root entry {
        person = cast(Person, jobj(self.person_jid)); message = cast(Message, jobj(self.message_jid));
        if message.is_comment { raise ValueError("Post required"); }
        if self.message_jid in [jid(m) for m in [person->:Likes:->[?:Message]]] { raise ValueError("Duplicate like"); }
        person +>:Likes(creation_date=self.creation_date):+> message; report None;
    }
}
walker U3 {
    has person_jid: str, message_jid: str, creation_date: int;
    can run with Root entry {
        person = cast(Person, jobj(self.person_jid)); message = cast(Message, jobj(self.message_jid));
        if not message.is_comment { raise ValueError("Comment required"); }
        if self.message_jid in [jid(m) for m in [person->:Likes:->[?:Message]]] { raise ValueError("Duplicate like"); }
        person +>:Likes(creation_date=self.creation_date):+> message; report None;
    }
}
walker U4 {
    has forum_id: int, title: str, creation_date: int, moderator_jid: str, tag_jids: list[str];
    can run with Root entry {
        if [-->[?:Forum, forum_id == self.forum_id]] { raise ValueError("Duplicate forum"); }
        forum = here ++> Forum(forum_id=self.forum_id, title=self.title, creation_date=self.creation_date);
        forum +>:HasModerator:+> cast(Person, jobj(self.moderator_jid));
        for key in self.tag_jids { forum +>:HasTag:+> cast(Tag, jobj(key)); }
        report None;
    }
}
walker U5 {
    has forum_jid: str, person_jid: str, join_date: int;
    can run with Root entry {
        forum = cast(Forum, jobj(self.forum_jid)); person = cast(Person, jobj(self.person_jid));
        if self.person_jid in [jid(p) for p in [forum->:HasMember:->[?:Person]]] { raise ValueError("Duplicate membership"); }
        forum +>:HasMember(join_date=self.join_date):+> person; report None;
    }
}
walker U6 {
    has message_id: int, content: str, image_file: str, creation_date: int,
        location_ip: str, browser: str, language: str, length: int,
        author_jid: str, forum_jid: str, country_jid: str, tag_jids: list[str];
    can run with Root entry {
        if [-->[?:Message, message_id == self.message_id]] { raise ValueError("Duplicate message"); }
        message = here ++> Message(message_id=self.message_id, content=self.content,
            image_file=self.image_file, creation_date=self.creation_date, is_comment=False,
            length=self.length, language=self.language, location_ip=self.location_ip, browser=self.browser);
        message +>:HasCreator:+> cast(Person, jobj(self.author_jid));
        cast(Forum, jobj(self.forum_jid)) +>:ContainerOf:+> message;
        message +>:LocatedIn:+> cast(Place, jobj(self.country_jid));
        for key in self.tag_jids { message +>:HasTag:+> cast(Tag, jobj(key)); }
        report None;
    }
}
walker U7 {
    has message_id: int, content: str, creation_date: int, location_ip: str,
        browser: str, length: int, author_jid: str, parent_jid: str,
        country_jid: str, tag_jids: list[str];
    can run with Root entry {
        if [-->[?:Message, message_id == self.message_id]] { raise ValueError("Duplicate message"); }
        message = here ++> Message(message_id=self.message_id, content=self.content,
            image_file="", creation_date=self.creation_date, is_comment=True, length=self.length,
            location_ip=self.location_ip, browser=self.browser);
        message +>:HasCreator:+> cast(Person, jobj(self.author_jid));
        message +>:ReplyOf:+> cast(Message, jobj(self.parent_jid));
        message +>:LocatedIn:+> cast(Place, jobj(self.country_jid));
        for key in self.tag_jids { message +>:HasTag:+> cast(Tag, jobj(key)); }
        report None;
    }
}
walker U8 {
    has person1_jid: str, person2_jid: str, creation_date: int;
    can run with Root entry {
        a = cast(Person, jobj(self.person1_jid)); b = cast(Person, jobj(self.person2_jid));
        if self.person1_jid == self.person2_jid or b.person_id in [p.person_id for p in _friends(a)] { raise ValueError("Duplicate or self friendship"); }
        a +>:Knows(creation_date=self.creation_date):+> b; report None;
    }
}
