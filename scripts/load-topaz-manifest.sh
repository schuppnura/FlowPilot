#!/bin/bash
# Load FlowPilot manifest into ***REMOVED*** directory

set -e

***REMOVED***_URL=${***REMOVED***_URL:-"http://localhost:9393"}
MANIFEST_FILE=${MANIFEST_FILE:-"/app/cfg/flowpilot-manifest.yaml"}

echo "Loading FlowPilot manifest into ***REMOVED***..."
echo "***REMOVED*** URL: $***REMOVED***_URL"
echo "Manifest file: $MANIFEST_FILE"

# Wait for ***REMOVED*** to be ready
echo "Waiting for ***REMOVED*** to be ready..."
for i in {1..30}; do
    if curl -sf "$***REMOVED***_URL/health" > /dev/null 2>&1; then
        echo "***REMOVED*** is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

# Load the manifest using the writer API
# The manifest needs to be loaded via the writer service
echo "Loading manifest..."

# Try loading via stdin
curl -X POST "$***REMOVED***_URL/api/v3/directory/import" \
    -H "Content-Type: application/json" \
    -d @- << 'EOF'
{
  "manifest": {
    "model": {
      "version": 3
    },
    "types": {
      "user": {
        "relations": {
          "delegate": {
            "union": {
              "child": [
                {
                  "this": {}
                }
              ]
            },
            "subject_type": "agent"
          }
        }
      },
      "agent": {},
      "workflow": {
        "relations": {
          "owner": {
            "union": {
              "child": [
                {
                  "this": {}
                }
              ]
            },
            "subject_type": "user"
          }
        },
        "permissions": {
          "can_execute": {
            "union": {
              "child": [
                {
                  "computed_userset": {
                    "relation": "delegate",
                    "object": "$subject_relation:owner"
                  }
                }
              ]
            }
          }
        }
      },
      "workflow_item": {
        "relations": {
          "workflow": {
            "union": {
              "child": [
                {
                  "this": {}
                }
              ]
            },
            "subject_type": "workflow"
          }
        },
        "permissions": {
          "can_execute": {
            "union": {
              "child": [
                {
                  "tuple_to_userset": {
                    "tupleset": {
                      "relation": "workflow"
                    },
                    "computed_userset": {
                      "relation": "can_execute"
                    }
                  }
                }
              ]
            }
          }
        }
      }
    }
  }
}
EOF

echo "Manifest loaded successfully!"
