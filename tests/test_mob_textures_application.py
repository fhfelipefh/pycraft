from mob_textures import apply_texture_recursively


class Node:
    def __init__(self):
        self.texture = None
        self._two_sided = False
        self.children = []

    def setTwoSided(self, value: bool):
        self._two_sided = bool(value)


def test_apply_texture_recursively_sets_texture_on_all_nodes():
    root = Node()
    a = Node(); b = Node()
    a1 = Node(); a2 = Node(); b1 = Node()
    root.children = [a, b]
    a.children = [a1, a2]
    b.children = [b1]

    sentinel_texture = object()
    apply_texture_recursively(root, sentinel_texture)

    def walk(n):
        yield n
        for c in n.children:
            yield from walk(c)

    for node in walk(root):
        assert node.texture is sentinel_texture
        assert node._two_sided is True
