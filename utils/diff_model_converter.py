import libcst as cst
from libcst import matchers as m
import importlib
import re
# Should we use the scope to figure out if classes are imported and inherited from
# then go from here, instead of visiting the classes?

def get_module_source_from_name(module_name: str) -> str:
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        return f"Module {module_name} not found"
    
    with open(spec.origin, 'r') as file:
        source_code = file.read()
    
    return source_code

from libcst import parse_module, CSTVisitor, CSTTransformer, ClassDef, Name


class ClassFinder(CSTVisitor):
    def __init__(self, python_module):
        self.module = python_module
        self.classes = {}

    def visit_ClassDef(self, node: ClassDef) -> None:
        self.classes[node.name.value] = node



class ReplaceNameTransformer(CSTTransformer):
    def __init__(self, old_name, new_name):
        self.new_name = new_name
        self.old_name = old_name
        self.regex = re.compile(re.escape(self.old_name), re.IGNORECASE)

    def preserve_case_replace(self, text):
        def replace(match):
            word = match.group()
            if word.isupper():
                return self.new_name.upper()
            elif word.istitle():
                return self.new_name.title()
            else:
                return self.new_name.lower()
        return self.regex.sub(replace, text)

    def leave_Name(self, original_node: Name, updated_node: Name) -> Name:
        # Replace 'Llama' with 'Cohere' in names
        updated_value = self.preserve_case_replace(updated_node.value)
        return updated_node.with_changes(value=updated_value)


def find_classes_in_file(module, old_id = "llama", new_id="gemma"):
    transformer = ReplaceNameTransformer(old_id, new_id)
    new_module = module.visit(transformer)

    class_finder = ClassFinder(new_module)
    new_module.visit(class_finder)
    return class_finder.classes, new_module

# Define a visitor to traverse the tree and find import statements
class ImportVisitor(cst.CSTVisitor):
    def __init__(self, python_module):
        self.transformers_imports = {}
        self.transformers_mapping = {}
        self.class_mapping = {}
        self.python_module = python_module

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        if m.matches(node.module, m.Attribute()):
            full_statement = self.python_module.code_for_node(node.module) 
            for imported_ in node.names:
                if "modeling_" in full_statement:
                    print(f"resolving import from {full_statement}")
                    if full_statement not in self.transformers_imports:
                        source_code = get_module_source_from_name(full_statement)
                        print(f"Source code found.")
                        tree = cst.parse_module(source_code)
                        self.transformers_imports[full_statement] = tree
                    self.transformers_mapping[self.python_module.code_for_node(imported_.name)] = full_statement

    def visit_Assign(self, node: cst.Assign) -> None:
        if m.matches(node.value, m.Name()):
            parent_package = self.transformers_mapping.get(node.value.value, None)
            if parent_package:
                print(f" Model assignment. Finding Source code of {node.value.value} to replace the assignment")
                classes, renamed_module = find_classes_in_file(self.transformers_imports[parent_package])
                self.class_mapping[self.python_module.code_for_node(node)] = classes[node.targets[0].target.value]

class DiffConverterTransformer(CSTTransformer):
    def __init__(self, mapping, python_module):
        super().__init__()
        self.mapping = mapping
        self.python_module = python_module

    def leave_SimpleStatementLine(self, original_node:cst.Assign, updated_node:cst.CSTNode):
        match updated_node:
            # note: this is just a plain copy & paste of the pattern as seen in the CST
            case cst.SimpleStatementLine(
                body=[
                    cst.Assign(
                        targets=[_],
                        value=_,
                    ),
                ],
            ):
                print("Happy")
                assign = self.python_module.code_for_node(original_node.body[0])
                node = original_node.body[0]
                if m.matches(node.value, m.Name()) and assign in self.mapping:
                    return self.mapping[assign]
        return updated_node

    def leave_ClassDef(self, original_node:cst.Assign, node):
        print(node.name)
        return node

if __name__ == "__main__":
    # Parse the Python file
    with open("/Users/arthurzucker/Work/transformers/src/transformers/models/gemma/diff_gemma.py", "r") as file:
        code = file.read()
    module = cst.parse_module(code)
    # find_modeling_imports(code)
    # Use the visitor to find imports
    visitor = ImportVisitor(module)
    module.visit(visitor)

    transformers = DiffConverterTransformer(visitor.class_mapping, module)
    new_mod = module.visit(transformers) 
    with open("result.py", "w") as f:
        f.write(new_mod.code)
    exit(0)
# Process the found imports
# for imported_name, import_node in visitor.transformers_imports:
#     print(f"Imported from transformers: {imported_name}")
#     # Extract the source code of the imported entity
#     entity_source_code = get_imported_entity_source(module, imported_name)
#     print(f"Source code of {imported_name}:")
#     print(entity_source_code)