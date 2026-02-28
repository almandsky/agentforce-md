"""Generate the bundle-meta.xml file content."""

BUNDLE_META_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<AiAuthoringBundle xmlns="http://soap.sforce.com/2006/04/metadata">
    <bundleType>AGENT</bundleType>
</AiAuthoringBundle>
"""


def generate_bundle_meta() -> str:
    """Return the constant bundle-meta.xml content."""
    return BUNDLE_META_XML
