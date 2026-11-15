"""Actual persistent Access payload without synthetic Visit dispatch."""
import json;
import os;
import from pathlib { Path }
import from tempfile { mkdtemp }
import from uuid { UUID }
import from jaclang.runtime.context { ExecutionContext }
import from jaclang.runtime.runtime { JacRuntime }
import from jaclang.runtime.archetype { Root }
import from jaclang.runtime.ttg_dependency_prefetch { dependency_prefetch }
import from .fixtures.ttg_access_walkers {
    AccessPerson, AccessPost, AccessFollow, AccessPostEdge,
    AccessProfile, AccessView, AccessGuard, AccessVisit,
    AccessLookup, AccessLookupGuard, AccessLookupMissing, AccessLookupRoot,
    AccessResume, AccessResumeBranch,
    AccessOwnsCondition, AccessOwnsValue, AccessOwnsOr, access_owns
}

def access_context(project: str) -> any {
    ctx = ExecutionContext(base_path_dir=project, full_target_path=str(Path(project, 'access.jac')));
    JacRuntime.exec_ctx = ctx;
    return ctx;
}

def access_fixture -> tuple[str, UUID] {
    project = mkdtemp(prefix='ttg-access-fixture-');
    ctx = access_context(project);
    try {
        p = root ++> AccessProfile();
        for i in range(2) {
            p +>:AccessFollow:+> AccessPerson(value=i, active=(i == 0));
        }
        for i in range(3) {
            p +>:AccessPostEdge:+> AccessPost(value=10 + i);
        }
        return (project, p.__jac__.id);
    } finally {
        ctx.close();
    }
}

def access_run(project: str, uid: UUID, wlk: any, enabled: bool, limit: int = 32, user_root: str = '') -> dict {
    ctx = access_context(project);
    try {
        if user_root {
            ctx.set_user_root(user_root);
        }
        origin = ctx.mem.get(uid).archetype;
        with dependency_prefetch(ctx, max_length=limit, mode='thread', workers=1, fused_sql=enabled) as run {
            origin spawn wlk;
        }
        assert not run.errors , str(run.errors);
        result = {'walker': type(wlk).__name__, 'enabled': enabled, 'limit': limit,
                  'seen': list(wlk.seen), 'summary': run.summary()};
        evidence = os.environ.get('TTG_ACCESS_EVIDENCE');
        if evidence {
            with open(evidence, 'a') as output {
                output.write(json.dumps(result) + '\n');
            }
        }
        return result;
    } finally {
        ctx.close();
    }
}

test "Access-only method reads prefetch nodes without scheduling visits" {
    (project, uid) = access_fixture();
    baseline = access_run(project, uid, AccessView(), False);
    result = access_run(project, uid, AccessView(), True);
    assert baseline['seen'] == result['seen'] == [0, 1, 10, 11, 12];
    assert result['summary']['fusion']['access_queries'] == 2;
    assert result['summary']['fusion']['access_payload_ids'] == 5;
    assert len(result['summary']['submitted_ids']) == 5;
}

test "Access guard and property filter exclude unused paths and rows" {
    (project, uid) = access_fixture();
    skipped = access_run(project, uid, AccessGuard(enabled=False), True);
    result = access_run(project, uid, AccessGuard(enabled=True), True);
    baseline = access_run(project, uid, AccessGuard(enabled=True), False);
    assert skipped['seen'] == [];
    assert skipped['summary']['submitted_ids'] == [];
    assert skipped['summary']['fusion']['access_guard_skips'] == 1;
    assert result['seen'] == baseline['seen'] == [0];
    assert result['summary']['fusion']['access_payload_ids'] == 1;
}

test "Access payload budget does not alter native output" {
    (project, uid) = access_fixture();
    result = access_run(project, uid, AccessView(), True, limit=2);
    assert result['seen'] == [0, 1, 10, 11, 12];
    assert len(result['summary']['submitted_ids']) <= 2;
}

test "Visit projection retains native scheduling and output" {
    (project, uid) = access_fixture();
    baseline = access_run(project, uid, AccessVisit(), False);
    result = access_run(project, uid, AccessVisit(), True);
    assert baseline['seen'] == result['seen'] == [10, 11, 12];
    assert result['summary']['fusion']['access_payload_ids'] == 0;
}

def access_lookup_fixture -> tuple[str, UUID, UUID] {
    (project, uid) = access_fixture();
    ctx = access_context(project);
    try {
        other = root ++> AccessProfile();
        other +>:AccessPostEdge:+> AccessPost(value=30);
        other +>:AccessPostEdge:+> AccessPost(value=31);
        return (project, uid, other.__jac__.id);
    } finally {
        ctx.close();
    }
}

test "jobj lookup binds helper graph origin and deduplicates payload" {
    (project, uid, target) = access_lookup_fixture();
    baseline = access_run(project, uid, AccessLookup(target_id=str(target)), False);
    for key in [str(target), target.hex] {
        result = access_run(project, uid, AccessLookup(target_id=key), True);
        assert baseline['seen'] == result['seen'] == [30, 31];
        assert result['summary']['fusion']['access_lookup_ids'] == 1;
        assert result['summary']['fusion']['access_lookup_skips'] == 1;
        assert result['summary']['fusion']['access_queries'] == 1;
        assert result['summary']['fusion']['access_payload_ids'] == 3;
        assert len(result['summary']['submitted_ids']) == 3;
    }
}

test "jobj payload respects false guards shared budget and cached origins" {
    (project, uid, target) = access_lookup_fixture();
    skipped = access_run(project, uid, AccessLookupGuard(target_id=str(target)), True);
    assert skipped['seen'] == [];
    assert skipped['summary']['submitted_ids'] == [];
    limited = access_run(project, uid, AccessLookup(target_id=str(target)), True, limit=1);
    assert limited['seen'] == [30, 31];
    assert len(limited['summary']['submitted_ids']) <= 1;
    cached = access_run(project, uid, AccessLookup(target_id=str(uid)), True);
    assert cached['seen'] == [10, 11, 12];
    assert cached['summary']['fusion']['access_lookup_ids'] == 0;
    rooted = access_run(project, uid, AccessLookupRoot(), True);
    assert rooted['seen'] == [1];
    assert rooted['summary']['fusion']['access_lookup_ids'] == 0;
}

test "jobj missing and invalid IDs preserve native None and exception" {
    (project, uid) = access_fixture();
    missing = '12345678123456781234567812345678';
    for enabled in [False, True] {
        result = access_run(project, uid, AccessLookupMissing(target_id=missing), enabled);
        assert result['seen'] == [-1];
        caught = False;
        try {
            access_run(project, uid, AccessLookupMissing(target_id='invalid-uuid'), enabled);
        } except ValueError {
            caught = True;
        }
        assert caught;
    }
}


test "Access resumes after actual guards and rebinds the mutated local" {
    (project, uid, target) = access_lookup_fixture();
    for replacement in ['', str(uid)] {
        baseline_w = AccessResume(target_id=str(target), replacement_id=replacement);
        baseline = access_run(project, uid, baseline_w, False);
        w = AccessResume(target_id=str(target), replacement_id=replacement);
        result = access_run(project, uid, w, True);
        assert result['seen'] == baseline['seen'] == ([10, 11, 12] if replacement else [30, 31]);
        assert w.condition_calls == baseline_w.condition_calls == 1;
        assert result['summary']['fusion']['access_resume_hooks'] == 1;
        assert result['summary']['fusion']['access_queries'] == 1;
        assert result['summary']['fusion']['access_payload_ids'] == (4 if replacement else 3);
        assert result['summary']['fusion']['access_declines'] == 0;
    }
}

test "Failed and raising guards never run the suffix prefetch hook" {
    (project, uid, target) = access_lookup_fixture();
    for enabled in [False, True] {
        for stop_after in [False, True] {
            w = AccessResume(target_id=str(target), allowed=stop_after, stop_after=stop_after);
            result = access_run(project, uid, w, enabled);
            assert result['seen'] == [];
            assert w.condition_calls == 1;
            assert result['summary']['fusion'].get('access_resume_hooks', 0) == 0;
            assert result['summary']['fusion']['access_queries'] == 0;
            assert result['summary']['fusion']['access_payload_ids'] == (1 if enabled else 0);
        }
        w = AccessResume(target_id=str(target), raise_guard=True);
        caught = False;
        try {
            access_run(project, uid, w, enabled);
        } except ValueError as error {
            caught = str(error) == 'native guard failure';
        }
        assert caught and w.condition_calls == 1 and w.seen == [];
    }
}

test "Unknown branch true and else hooks preserve selected native path" {
    (project, uid, target) = access_lookup_fixture();
    for allowed in [False, True] {
        baseline = access_run(project, uid, AccessResumeBranch(target_id=str(target), allowed=allowed), False);
        w = AccessResumeBranch(target_id=str(target), allowed=allowed);
        result = access_run(project, uid, w, True);
        assert result['seen'] == baseline['seen'] == ([30, 31] if allowed else [10, 11, 12]);
        assert w.condition_calls == 1;
        assert result['summary']['fusion']['access_resume_hooks'] == 1;
        assert result['summary']['fusion']['access_queries'] == 1;
        assert result['summary']['fusion']['access_declines'] == 0;
    }
}


def access_ownership_fixture -> tuple[str, UUID, UUID, UUID, UUID] {
    project = mkdtemp(prefix='ttg-access-ownership-fixture-');
    ctx = access_context(project);
    try {
        actor: any = Root().__jac__;
        actor.persistent = True;
        setattr(actor, 'root', actor.id);
        ctx.mem.put(actor);
        ctx.mem.commit();
        ctx.set_user_root(str(actor.id));
        origin = root ++> AccessProfile();
        wrong = origin +>:AccessPostEdge:+> AccessPost(value=10);
        other = root ++> AccessProfile();
        other +>:AccessPostEdge:+> AccessPost(value=30);
        root ++> AccessPerson(value=99);
        root ++> AccessPerson(value=100);
        return (project, origin.__jac__.id, other.__jac__.id, wrong.__jac__.id, actor.id);
    } finally {
        ctx.close();
    }
}

test "Condition and value calls share guarded Access and never execute helper twice" {
    import sys;
    import from unittest.mock { patch }
    (project, uid, target, wrong, actor) = access_ownership_fixture();
    module = sys.modules[access_owns.__module__];
    for kind in [AccessOwnsCondition, AccessOwnsValue] {
        baseline = access_run(project, uid, kind(target_id=str(target)), False, user_root=str(actor));
        with patch.object(module, 'access_owns', wraps=access_owns) as spy {
            result = access_run(project, uid, kind(target_id=str(target)), True, user_root=str(actor));
            assert spy.call_count == 1;
        }
        assert result['seen'] == baseline['seen'] == [1];
        assert result['summary']['fusion']['access_queries'] == 1;
        assert result['summary']['fusion']['access_payload_ids'] == 3;
        assert result['summary']['fusion']['access_resume_hooks'] == 1;
        assert result['summary']['fusion'].get('access_guard_waits', 0) == 1;
        assert result['summary']['fusion']['access_declines'] == 0;
    }
}

test "Boolean and or short circuits skip helper and its graph reads" {
    import sys;
    import from unittest.mock { patch }
    (project, uid, target, wrong, actor) = access_ownership_fixture();
    module = sys.modules[access_owns.__module__];
    for (w, expected) in [
        (AccessOwnsCondition(target_id=str(target), enabled=False), [0]),
        (AccessOwnsOr(target_id=str(target)), [1])
    ] {
        with patch.object(module, 'access_owns', wraps=access_owns) as spy {
            result = access_run(project, uid, w, True, user_root=str(actor));
            assert spy.call_count == 0;
        }
        assert result['seen'] == expected;
        assert result['summary']['fusion']['access_queries'] == 0;
        assert result['summary']['fusion']['access_payload_ids'] == 1;
    }
}

test "Wrong type and missing object short circuit ownership Access" {
    (project, uid, target, wrong, actor) = access_ownership_fixture();
    for key in [str(wrong), '00000000-0000-0000-0000-000000000091'] {
        baseline = access_run(project, uid, AccessOwnsCondition(target_id=key), False, user_root=str(actor));
        result = access_run(project, uid, AccessOwnsCondition(target_id=key), True, user_root=str(actor));
        assert result['seen'] == baseline['seen'] == [0];
        assert result['summary']['fusion']['access_queries'] == 0;
        assert result['summary']['fusion']['access_payload_ids'] == 1;
        assert result['summary']['fusion']['access_guard_skips'] >= 1;
        assert result['summary']['fusion']['access_declines'] == 0;
    }
}
