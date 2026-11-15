"""Standard permissions are the runtime contract; no persisted type census."""
import from jaclang.runtime.archetype { Archetype, NodeArchetype }


def standard_node_access(node_type: any) -> bool {
    if type(node_type) is not type or not issubclass(node_type, NodeArchetype) {
        return False;
    }
    Archetype.require_standard_access(node_type);
    return True;
}
