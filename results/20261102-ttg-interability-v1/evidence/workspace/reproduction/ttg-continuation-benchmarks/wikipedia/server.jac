"""BenchBase Wikipedia procedure ports; sequential graph research adapter.

Preserves mutation order, watcher branch and logging bindings; the group-read
statement repair is explicitly recorded in fixture provenance. Native auth identifies the isolated operator; benchmark users are data.
"""
import datetime;
import from fixture_loader { seed_graph, remove_node }
node WikiUser { has user_id: int, user_name: str, user_touched: str, user_editcount: int; }
node UserGroup { has user_id: int, group_name: str; }
node Page { has page_id: int, page_namespace: int, page_title: str, page_latest: int,
    page_touched: str, page_is_new: int, page_is_redirect: int, page_len: int; }
node PageRestriction { has pr_page: int, pr_type: str; }
node IPBlock { has ipb_user: int, ipb_address: str, ipb_expiry: str; }
node Text { has old_id: int, old_page: int, old_text: str, old_flags: str; }
node Revision {
    has rev_id: int, rev_page: int, rev_text_id: int, rev_comment: str,
        rev_minor_edit: int, rev_user: int, rev_user_text: str, rev_timestamp: str,
        rev_deleted: int, rev_len: int, rev_parent_id: int;
}
node Watch { has wl_user: int, wl_namespace: int, wl_title: str, wl_notificationtimestamp: str | None = None; }
node RecentChange {
    has rc_timestamp: str, rc_cur_time: str, rc_namespace: int, rc_title: str,
        rc_type: int, rc_minor: int, rc_cur_id: int, rc_user: int, rc_user_text: str,
        rc_comment: str, rc_this_oldid: int, rc_last_oldid: int, rc_bot: int,
        rc_moved_to_ns: int, rc_moved_to_title: str, rc_ip: str, rc_old_len: int,
        rc_new_len: int;
}
node Log {
    has log_type: str, log_action: str, log_timestamp: str, log_user: int,
        log_user_text: str, log_namespace: int, log_title: str, log_page: int,
        log_comment: str, log_params: str;
}
edge HasRevision {}
edge HasText {}
def _now() -> str { return datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H%M%S"); }
walker Seed {
    has directory: str;
    can seed with Root entry {
        if [-->] { raise ValueError("Fixture root is not empty"); }
        report seed_graph(self.directory,
            {"WikiUser": WikiUser, "UserGroup": UserGroup, "Page": Page,
             "PageRestriction": PageRestriction, "IPBlock": IPBlock, "Text": Text,
             "Revision": Revision, "Watch": Watch, "RecentChange": RecentChange, "Log": Log},
            {"HasRevision": HasRevision, "HasText": HasText});
    }
}

walker GetPageAnonymous {
    has user_ip: str, namespace: int, title: str, user_id: int = 0,
        for_select: bool = False, user_text: str = "", page_id: int = -1, latest_id: int = -1,
        text_id: int = -1, revision_id: int = -1, article: dict = {};
    can start with Root entry {
        self.user_text = self.user_ip;
        pages = [-->[?:Page, page_namespace == self.namespace, page_title == self.title]];
        if not pages { raise ValueError("Invalid page"); }
        visit [pages[0]];
    }
    can page with Page entry {
        self.page_id = here.page_id; self.latest_id = here.page_latest;
        restrictions = [root-->[?:PageRestriction, pr_page == self.page_id]];
        for restriction in restrictions { restriction_type = restriction.pr_type; }
        blocks = [root-->[?:IPBlock, ipb_address == self.user_ip]];
        for block in blocks { expiry = block.ipb_expiry; }
        revisions = [here->:HasRevision:->[?:Revision, rev_id == self.latest_id, rev_page == self.page_id]];
        if not revisions { raise ValueError("Invalid revision"); }
        visit [revisions[0]];
    }
    can revision with Revision entry {
        self.revision_id = here.rev_id; self.text_id = here.rev_text_id;
        texts = [here->:HasText:->[?:Text, old_id == self.text_id]];
        if not texts { raise ValueError("Missing text"); }
        visit [texts[0]];
    }
    can text with Text entry {
        if not self.for_select {
            self.article = {"userText": self.user_text, "pageId": self.page_id,
                "oldText": here.old_text, "textId": self.text_id, "revisionId": self.revision_id};
        }
    }
    can finish with Root exit { report None if self.for_select else self.article; }
}

walker GetPageAuthenticated {
    has user_ip: str, namespace: int, title: str, user_id: int = 0,
        for_select: bool = False, user_text: str = "", page_id: int = -1, latest_id: int = -1,
        text_id: int = -1, revision_id: int = -1, article: dict = {};
    can start with Root entry {
        self.user_text = self.user_ip;
        if self.user_id > 0 {
            users = [-->[?:WikiUser, user_id == self.user_id]];
            if not users { raise ValueError("Invalid user"); }
            self.user_text = users[0].user_name;
            groups = [-->[?:UserGroup, user_id == self.user_id]];
            for group in groups { assert group.group_name != None; }
        }
        pages = [-->[?:Page, page_namespace == self.namespace, page_title == self.title]];
        if not pages { raise ValueError("Invalid page"); }
        visit [pages[0]];
    }
    can page with Page entry {
        self.page_id = here.page_id; self.latest_id = here.page_latest;
        restrictions = [root-->[?:PageRestriction, pr_page == self.page_id]];
        for restriction in restrictions { restriction_type = restriction.pr_type; }
        blocks = [root-->[?:IPBlock, ipb_user == self.user_id]];
        for block in blocks { expiry = block.ipb_expiry; }
        revisions = [here->:HasRevision:->[?:Revision, rev_id == self.latest_id, rev_page == self.page_id]];
        if not revisions { raise ValueError("Invalid revision"); }
        visit [revisions[0]];
    }
    can revision with Revision entry {
        self.revision_id = here.rev_id; self.text_id = here.rev_text_id;
        texts = [here->:HasText:->[?:Text, old_id == self.text_id]];
        if not texts { raise ValueError("Missing text"); }
        visit [texts[0]];
    }
    can text with Text entry {
        if not self.for_select {
            self.article = {"userText": self.user_text, "pageId": self.page_id,
                "oldText": here.old_text, "textId": self.text_id, "revisionId": self.revision_id};
        }
    }
    can finish with Root exit { report None if self.for_select else self.article; }
}
walker AddWatchList {
    has user_id: int, namespace: int, title: str;
    can run with Root entry {
        if self.user_id > 0 {
            namespaces = [self.namespace] + ([1] if self.namespace == 0 else []);
            for ns in namespaces {
                if [-->[?:Watch, wl_user == self.user_id, wl_namespace == ns, wl_title == self.title]] {
                    raise ValueError("Duplicate watch");
                }
                here ++> Watch(wl_user=self.user_id, wl_namespace=ns, wl_title=self.title);
            }
            for user in [-->[?:WikiUser, user_id == self.user_id]] { user.user_touched = _now(); }
        }
        report None;
    }
}
walker RemoveWatchList {
    has user_id: int, namespace: int, title: str;
    can run with Root entry {
        if self.user_id > 0 {
            namespaces = [self.namespace] + ([1] if self.namespace == 0 else []);
            for ns in namespaces {
                for watch in [-->[?:Watch, wl_user == self.user_id, wl_namespace == ns, wl_title == self.title]] { remove_node(watch); }
            }
            for user in [-->[?:WikiUser, user_id == self.user_id]] { user.user_touched = _now(); }
        }
        report None;
    }
}
walker UpdatePage {
    has text_id: int, page_id: int, page_title: str, page_text: str, namespace: int,
        user_id: int, user_ip: str, user_text: str, revision_id: int,
        revision_comment: str, minor_edit: int;
    can run with Root entry {
        timestamp = _now();
        text_id = 1 + max([0] + [t.old_id for t in [-->[?:Text]]]);
        revision_id = 1 + max([0] + [r.rev_id for r in [-->[?:Revision]]]);
        text = here ++> Text(old_id=text_id, old_page=self.page_id, old_text=self.page_text, old_flags="utf-8");
        revision = here ++> Revision(rev_id=revision_id, rev_page=self.page_id, rev_text_id=text_id,
            rev_comment=self.revision_comment[:254], rev_minor_edit=self.minor_edit, rev_user=self.user_id,
            rev_user_text=self.user_text, rev_timestamp=timestamp, rev_deleted=0,
            rev_len=len(self.page_text), rev_parent_id=self.revision_id);
        revision +>:HasText:+> text;
        for page in [-->[?:Page, page_id == self.page_id]] {
            page +>:HasRevision:+> revision;
            page.page_latest = revision_id; page.page_touched = timestamp;
            page.page_is_new = 0; page.page_is_redirect = 0; page.page_len = len(self.page_text);
        }
        here ++> RecentChange(rc_timestamp=timestamp, rc_cur_time=timestamp,
            rc_namespace=self.namespace, rc_title=self.page_title, rc_type=0, rc_minor=0,
            rc_cur_id=self.page_id, rc_user=self.user_id, rc_user_text=self.user_text,
            rc_comment=self.revision_comment, rc_this_oldid=text_id, rc_last_oldid=self.text_id,
            rc_bot=0, rc_moved_to_ns=0, rc_moved_to_title="", rc_ip=self.user_ip,
            rc_old_len=len(self.page_text), rc_new_len=len(self.page_text));
        watchers = [-->[?:Watch, wl_title == self.page_title, wl_namespace == self.namespace,
            wl_user != self.user_id, wl_notificationtimestamp == None]];
        for watcher in watchers { watcher.wl_notificationtimestamp = timestamp; }
        for watcher in watchers {
            users = [-->[?:WikiUser, user_id == watcher.wl_user]];
            for user in users { user_name = user.user_name; }
        }
        # Preserve this pinned variant's page-title/user-text parameter binding.
        here ++> Log(log_type="patrol", log_action="patrol", log_timestamp=timestamp,
            log_user=self.user_id, log_user_text=self.page_title, log_namespace=self.namespace,
            log_title=self.user_text, log_page=self.page_id, log_comment="",
            log_params=str(revision_id) + "\n" + str(self.revision_id) + "\n1");
        for user in [-->[?:WikiUser, user_id == self.user_id]] {
            user.user_editcount += 1; user.user_touched = timestamp;
        }
        report None;
    }
}
