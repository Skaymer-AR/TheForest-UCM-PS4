using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace UcmUnitySerializationProbe
{
    [Serializable]
    public sealed class ProbeSnapshot
    {
        public int intValue;
        public bool boolValue;
        public float floatValue;
        public string stringValue;
        public string mode;
        public float vectorX;
        public float vectorY;
        public float vectorZ;
        public float colorR;
        public float colorG;
        public float colorB;
        public float colorA;
        public float rootX;
        public float rootY;
        public float rootZ;
        public string referenceTarget;
        public int targetAId;
        public int targetBId;
        public int stateCount;
        public string firstState;
        public int firstStateId;
        public string firstTransitionEvent;
        public string firstTransitionTarget;
        public string firstActionKind;
        public string firstActionLabel;
        public float firstActionScalar;
        public string secondState;
        public int secondStateId;
        public string secondTransitionEvent;
        public string secondTransitionTarget;
        public string nestedActionKind;
        public string nestedActionLabel;
        public float nestedActionScalar;
    }

    [Serializable]
    public sealed class ProbeVariant
    {
        public string name;
        public string changedField;
        public string scenePath;
        public string sceneSha256;
        public long sceneBytes;
        public string prefabPath;
        public string prefabSha256;
        public long prefabBytes;
        public string bundlePath;
        public string bundleSha256;
        public long bundleBytes;
        public ProbeSnapshot snapshot;
    }

    [Serializable]
    public sealed class ProbeReport
    {
        public int schemaVersion;
        public string generatedBy;
        public string unityVersion;
        public string serializationMode;
        public string buildTarget;
        public bool syntheticOnly;
        public bool capturedAfterSaveAndReload;
        public int expectedSerializedFileFormat;
        public string outputKinds;
        public ProbeVariant[] variants;
    }

    public static class SyntheticSerializationDriver
    {
        private const string ExpectedUnityVersion = "5.6.6f2";
        private const string GeneratedAssetRoot = "Assets/__UcmSerializationProbeGenerated";
        private const string SceneRootName = "UCM_SERIALIZATION_PROBE_ROOT";

        private sealed class Case
        {
            public string name;
            public string changedField;
        }

        private static readonly Case[] Cases = new Case[]
        {
            new Case { name = "baseline", changedField = "" },
            new Case { name = "int-value", changedField = "intValue" },
            new Case { name = "bool-value", changedField = "boolValue" },
            new Case { name = "float-value", changedField = "floatValue" },
            new Case { name = "string-value", changedField = "stringValue" },
            new Case { name = "enum-value", changedField = "mode" },
            new Case { name = "vector-value", changedField = "vectorValue" },
            new Case { name = "color-value", changedField = "colorValue" },
            new Case { name = "object-reference", changedField = "referenceTarget" },
            new Case { name = "nested-state-field", changedField = "states[1].action.label" }
        };

        public static void RunBatch()
        {
            try
            {
                Run();
                Debug.Log("Unity 5.6.6f2 synthetic serialization probe: PASS");
                EditorApplication.Exit(0);
            }
            catch (Exception exception)
            {
                Debug.LogException(exception);
                EditorApplication.Exit(1);
            }
        }

        private static void Run()
        {
            if (!String.Equals(Application.unityVersion, ExpectedUnityVersion,
                    StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    "Expected Unity " + ExpectedUnityVersion + ", got " + Application.unityVersion);
            }

            string outputRoot = Environment.GetEnvironmentVariable("UCM_UNITY_PROBE_OUTPUT");
            if (String.IsNullOrEmpty(outputRoot))
            {
                throw new InvalidOperationException("Set UCM_UNITY_PROBE_OUTPUT to an external output directory.");
            }
            outputRoot = Path.GetFullPath(outputRoot);
            string assetsRoot = Path.GetFullPath(Application.dataPath) + Path.DirectorySeparatorChar;
            if (outputRoot.StartsWith(assetsRoot, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("Probe output must not be inside the Unity Assets directory.");
            }

            EditorSettings.serializationMode = SerializationMode.ForceText;
            if (AssetDatabase.IsValidFolder(GeneratedAssetRoot))
            {
                AssetDatabase.DeleteAsset(GeneratedAssetRoot);
            }
            AssetDatabase.CreateFolder("Assets", "__UcmSerializationProbeGenerated");
            Directory.CreateDirectory(outputRoot);
            Directory.CreateDirectory(Path.Combine(outputRoot, "scenes"));
            Directory.CreateDirectory(Path.Combine(outputRoot, "prefabs"));
            Directory.CreateDirectory(Path.Combine(outputRoot, "bundles"));

            ProbeVariant[] variants = new ProbeVariant[Cases.Length];
            AssetBundleBuild[] bundleBuilds = new AssetBundleBuild[Cases.Length];
            ProbeSnapshot baseline = null;

            for (int index = 0; index < Cases.Length; index++)
            {
                Case testCase = Cases[index];
                string assetStem = "Probe_" + testCase.name;
                string sceneAssetPath = GeneratedAssetRoot + "/" + assetStem + ".unity";
                string prefabAssetPath = GeneratedAssetRoot + "/" + assetStem + ".prefab";
                Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                SyntheticMenuHost host = CreateGraph();
                ApplyMutation(host, testCase.name);

                ProbeSnapshot expected = Capture(host);
                if (index == 0)
                {
                    baseline = expected;
                }
                else
                {
                    AssertExactlyOneChangedField(baseline, expected, testCase.changedField);
                }

                if (!EditorSceneManager.SaveScene(scene, sceneAssetPath))
                {
                    throw new IOException("Unity Editor did not save scene " + sceneAssetPath);
                }
                UnityEngine.Object prefab = PrefabUtility.CreatePrefab(prefabAssetPath, host.gameObject);
                if (prefab == null)
                {
                    throw new IOException("Unity Editor did not create prefab " + prefabAssetPath);
                }
                AssetDatabase.SaveAssets();
                AssetDatabase.Refresh();
                AssetDatabase.ImportAsset(sceneAssetPath);
                AssetDatabase.ImportAsset(prefabAssetPath);

                GameObject prefabRoot = AssetDatabase.LoadAssetAtPath<GameObject>(prefabAssetPath);
                if (prefabRoot == null)
                {
                    throw new InvalidDataException("Unity Editor could not reload prefab " + prefabAssetPath);
                }
                SyntheticMenuHost prefabHost = prefabRoot.GetComponent<SyntheticMenuHost>();
                AssertSnapshot(expected, Capture(prefabHost), "reloaded prefab " + testCase.name);

                EditorSceneManager.OpenScene(sceneAssetPath, OpenSceneMode.Single);
                GameObject sceneRoot = GameObject.Find(SceneRootName);
                if (sceneRoot == null)
                {
                    throw new InvalidDataException("Unity Editor could not reopen scene " + sceneAssetPath);
                }
                SyntheticMenuHost sceneHost = sceneRoot.GetComponent<SyntheticMenuHost>();
                AssertSnapshot(expected, Capture(sceneHost), "reopened scene " + testCase.name);

                string savedScene = CopyArtifact(sceneAssetPath,
                    Path.Combine(outputRoot, "scenes", testCase.name + ".unity"));
                CopyArtifact(sceneAssetPath + ".meta",
                    Path.Combine(outputRoot, "scenes", testCase.name + ".unity.meta"));
                string savedPrefab = CopyArtifact(prefabAssetPath,
                    Path.Combine(outputRoot, "prefabs", testCase.name + ".prefab"));
                CopyArtifact(prefabAssetPath + ".meta",
                    Path.Combine(outputRoot, "prefabs", testCase.name + ".prefab.meta"));

                ProbeVariant record = new ProbeVariant();
                record.name = testCase.name;
                record.changedField = testCase.changedField;
                record.scenePath = Relative(outputRoot, savedScene);
                record.sceneSha256 = Sha256(savedScene);
                record.sceneBytes = new FileInfo(savedScene).Length;
                record.prefabPath = Relative(outputRoot, savedPrefab);
                record.prefabSha256 = Sha256(savedPrefab);
                record.prefabBytes = new FileInfo(savedPrefab).Length;
                record.snapshot = Capture(prefabHost);
                variants[index] = record;

                AssetBundleBuild bundleBuild = new AssetBundleBuild();
                bundleBuild.assetBundleName = "ucm-probe-" + testCase.name;
                bundleBuild.assetNames = new string[] { prefabAssetPath };
                bundleBuilds[index] = bundleBuild;
            }

            string bundleDirectory = Path.Combine(outputRoot, "bundles");
            AssetBundleManifest manifest = BuildPipeline.BuildAssetBundles(
                bundleDirectory, bundleBuilds,
                BuildAssetBundleOptions.UncompressedAssetBundle |
                    BuildAssetBundleOptions.DisableWriteTypeTree,
                EditorUserBuildSettings.activeBuildTarget);
            if (manifest == null)
            {
                throw new InvalidDataException("Unity BuildPipeline returned no AssetBundleManifest.");
            }

            for (int index = 0; index < Cases.Length; index++)
            {
                string bundleName = "ucm-probe-" + Cases[index].name;
                string bundleFile = Path.Combine(bundleDirectory, bundleName);
                if (!File.Exists(bundleFile))
                {
                    throw new FileNotFoundException("Unity did not emit AssetBundle " + bundleName, bundleFile);
                }
                variants[index].bundlePath = Relative(outputRoot, bundleFile);
                variants[index].bundleSha256 = Sha256(bundleFile);
                variants[index].bundleBytes = new FileInfo(bundleFile).Length;
            }

            ProbeReport report = new ProbeReport();
            report.schemaVersion = 1;
            report.generatedBy = "UnityEditor";
            report.unityVersion = Application.unityVersion;
            report.serializationMode = EditorSettings.serializationMode.ToString();
            report.buildTarget = EditorUserBuildSettings.activeBuildTarget.ToString();
            report.syntheticOnly = true;
            report.capturedAfterSaveAndReload = true;
            report.expectedSerializedFileFormat = 17;
            report.outputKinds = "Unity YAML scenes/prefabs and BuildPipeline AssetBundles; not loose .assets files";
            report.variants = variants;
            string reportPath = Path.Combine(outputRoot, "unity-editor-report.json");
            File.WriteAllText(reportPath, JsonUtility.ToJson(report, true), new UTF8Encoding(false));
        }

        private static SyntheticMenuHost CreateGraph()
        {
            GameObject root = new GameObject(SceneRootName);
            root.transform.position = new Vector3(1.25f, -2.5f, 3.75f);
            SyntheticMenuHost host = root.AddComponent<SyntheticMenuHost>();
            host.intValue = 101;
            host.boolValue = true;
            host.floatValue = 1.25f;
            host.stringValue = "baseline";
            host.mode = SyntheticProbeMode.Closed;
            host.vectorValue = new Vector3(1.25f, -2.5f, 3.75f);
            host.colorValue = new Color(0.1f, 0.2f, 0.3f, 1.0f);

            GameObject targetAObject = new GameObject("SyntheticTargetA");
            targetAObject.transform.SetParent(root.transform, false);
            SyntheticProbeTarget targetA = targetAObject.AddComponent<SyntheticProbeTarget>();
            targetA.targetId = 1;

            GameObject targetBObject = new GameObject("SyntheticTargetB");
            targetBObject.transform.SetParent(root.transform, false);
            SyntheticProbeTarget targetB = targetBObject.AddComponent<SyntheticProbeTarget>();
            targetB.targetId = 2;
            host.referenceTarget = targetA;

            SyntheticProbeAction closedAction = new SyntheticProbeAction();
            closedAction.kind = "Input";
            closedAction.label = "SyntheticOpenAction";
            closedAction.scalar = 0.0f;
            SyntheticProbeState closed = new SyntheticProbeState();
            closed.name = "Closed";
            closed.id = 0;
            closed.transitionEvent = "Open";
            closed.transitionTarget = "Main";
            closed.action = closedAction;

            SyntheticProbeAction mainAction = new SyntheticProbeAction();
            mainAction.kind = "Display";
            mainAction.label = "Observe";
            mainAction.scalar = 2.5f;
            SyntheticProbeState main = new SyntheticProbeState();
            main.name = "Main";
            main.id = 1;
            main.transitionEvent = "Close";
            main.transitionTarget = "Closed";
            main.action = mainAction;
            host.states = new SyntheticProbeState[] { closed, main };
            return host;
        }

        private static void ApplyMutation(SyntheticMenuHost host, string caseName)
        {
            if (caseName == "int-value") host.intValue = 202;
            else if (caseName == "bool-value") host.boolValue = false;
            else if (caseName == "float-value") host.floatValue = 9.5f;
            else if (caseName == "string-value") host.stringValue = "changed-string";
            else if (caseName == "enum-value") host.mode = SyntheticProbeMode.Open;
            else if (caseName == "vector-value") host.vectorValue = new Vector3(7.0f, 8.0f, 9.0f);
            else if (caseName == "color-value") host.colorValue = new Color(0.9f, 0.8f, 0.7f, 0.6f);
            else if (caseName == "object-reference")
                host.referenceTarget = GameObject.Find("SyntheticTargetB").GetComponent<SyntheticProbeTarget>();
            else if (caseName == "nested-state-field") host.states[1].action.label = "Navigate";
            else if (caseName != "baseline")
                throw new ArgumentException("Unknown probe variant " + caseName);
        }

        private static ProbeSnapshot Capture(SyntheticMenuHost host)
        {
            if (host == null || host.referenceTarget == null || host.states == null || host.states.Length != 2)
            {
                throw new InvalidDataException("Synthetic host references or state graph did not survive serialization.");
            }
            Transform targetATransform = host.transform.Find("SyntheticTargetA");
            Transform targetBTransform = host.transform.Find("SyntheticTargetB");
            if (targetATransform == null || targetBTransform == null ||
                targetATransform.gameObject.GetComponent<SyntheticProbeTarget>() == null ||
                targetBTransform.gameObject.GetComponent<SyntheticProbeTarget>() == null ||
                host.states[0] == null || host.states[0].action == null ||
                host.states[1] == null || host.states[1].action == null)
            {
                throw new InvalidDataException("Synthetic child references or nested state records did not survive serialization.");
            }
            ProbeSnapshot snapshot = new ProbeSnapshot();
            snapshot.intValue = host.intValue;
            snapshot.boolValue = host.boolValue;
            snapshot.floatValue = host.floatValue;
            snapshot.stringValue = host.stringValue;
            snapshot.mode = host.mode.ToString();
            snapshot.vectorX = host.vectorValue.x;
            snapshot.vectorY = host.vectorValue.y;
            snapshot.vectorZ = host.vectorValue.z;
            snapshot.colorR = host.colorValue.r;
            snapshot.colorG = host.colorValue.g;
            snapshot.colorB = host.colorValue.b;
            snapshot.colorA = host.colorValue.a;
            snapshot.rootX = host.transform.position.x;
            snapshot.rootY = host.transform.position.y;
            snapshot.rootZ = host.transform.position.z;
            snapshot.referenceTarget = host.referenceTarget.name;
            snapshot.targetAId = targetATransform.gameObject.GetComponent<SyntheticProbeTarget>().targetId;
            snapshot.targetBId = targetBTransform.gameObject.GetComponent<SyntheticProbeTarget>().targetId;
            snapshot.stateCount = host.states.Length;
            snapshot.firstState = host.states[0].name;
            snapshot.firstStateId = host.states[0].id;
            snapshot.firstTransitionEvent = host.states[0].transitionEvent;
            snapshot.firstTransitionTarget = host.states[0].transitionTarget;
            snapshot.firstActionKind = host.states[0].action.kind;
            snapshot.firstActionLabel = host.states[0].action.label;
            snapshot.firstActionScalar = host.states[0].action.scalar;
            snapshot.secondState = host.states[1].name;
            snapshot.secondStateId = host.states[1].id;
            snapshot.secondTransitionEvent = host.states[1].transitionEvent;
            snapshot.secondTransitionTarget = host.states[1].transitionTarget;
            snapshot.nestedActionKind = host.states[1].action.kind;
            snapshot.nestedActionLabel = host.states[1].action.label;
            snapshot.nestedActionScalar = host.states[1].action.scalar;
            return snapshot;
        }

        private static void AssertExactlyOneChangedField(ProbeSnapshot baseline,
            ProbeSnapshot actual, string expectedField)
        {
            string changed = null;
            int count = 0;
            CompareField(ref count, ref changed, "intValue", baseline.intValue != actual.intValue);
            CompareField(ref count, ref changed, "boolValue", baseline.boolValue != actual.boolValue);
            CompareField(ref count, ref changed, "floatValue", !Near(baseline.floatValue, actual.floatValue));
            CompareField(ref count, ref changed, "stringValue", baseline.stringValue != actual.stringValue);
            CompareField(ref count, ref changed, "mode", baseline.mode != actual.mode);
            bool vectorChanged = !Near(baseline.vectorX, actual.vectorX) ||
                !Near(baseline.vectorY, actual.vectorY) || !Near(baseline.vectorZ, actual.vectorZ);
            CompareField(ref count, ref changed, "vectorValue", vectorChanged);
            bool colorChanged = !Near(baseline.colorR, actual.colorR) ||
                !Near(baseline.colorG, actual.colorG) || !Near(baseline.colorB, actual.colorB) ||
                !Near(baseline.colorA, actual.colorA);
            CompareField(ref count, ref changed, "colorValue", colorChanged);
            bool rootTransformChanged = !Near(baseline.rootX, actual.rootX) ||
                !Near(baseline.rootY, actual.rootY) || !Near(baseline.rootZ, actual.rootZ);
            CompareField(ref count, ref changed, "rootTransform", rootTransformChanged);
            CompareField(ref count, ref changed, "referenceTarget",
                baseline.referenceTarget != actual.referenceTarget);
            CompareField(ref count, ref changed, "targetAId", baseline.targetAId != actual.targetAId);
            CompareField(ref count, ref changed, "targetBId", baseline.targetBId != actual.targetBId);
            CompareField(ref count, ref changed, "stateCount", baseline.stateCount != actual.stateCount);
            CompareField(ref count, ref changed, "states[0].name", baseline.firstState != actual.firstState);
            CompareField(ref count, ref changed, "states[0].id", baseline.firstStateId != actual.firstStateId);
            CompareField(ref count, ref changed, "states[0].transitionEvent",
                baseline.firstTransitionEvent != actual.firstTransitionEvent);
            CompareField(ref count, ref changed, "states[0].transitionTarget",
                baseline.firstTransitionTarget != actual.firstTransitionTarget);
            CompareField(ref count, ref changed, "states[0].action.kind",
                baseline.firstActionKind != actual.firstActionKind);
            CompareField(ref count, ref changed, "states[0].action.label",
                baseline.firstActionLabel != actual.firstActionLabel);
            CompareField(ref count, ref changed, "states[0].action.scalar",
                !Near(baseline.firstActionScalar, actual.firstActionScalar));
            CompareField(ref count, ref changed, "states[1].name", baseline.secondState != actual.secondState);
            CompareField(ref count, ref changed, "states[1].id", baseline.secondStateId != actual.secondStateId);
            CompareField(ref count, ref changed, "states[1].transitionEvent",
                baseline.secondTransitionEvent != actual.secondTransitionEvent);
            CompareField(ref count, ref changed, "states[1].transitionTarget",
                baseline.secondTransitionTarget != actual.secondTransitionTarget);
            CompareField(ref count, ref changed, "states[1].action.kind",
                baseline.nestedActionKind != actual.nestedActionKind);
            CompareField(ref count, ref changed, "states[1].action.label",
                baseline.nestedActionLabel != actual.nestedActionLabel);
            CompareField(ref count, ref changed, "states[1].action.scalar",
                !Near(baseline.nestedActionScalar, actual.nestedActionScalar));
            if (count != 1 || changed != expectedField)
            {
                throw new InvalidDataException("Variant " + expectedField +
                    " changed " + count + " snapshot fields; expected exactly itself.");
            }
        }

        private static void CompareField(ref int count, ref string changed,
            string field, bool differs)
        {
            if (differs)
            {
                count++;
                changed = field;
            }
        }

        private static void AssertSnapshot(ProbeSnapshot expected, ProbeSnapshot actual, string context)
        {
            if (expected.intValue != actual.intValue || expected.boolValue != actual.boolValue ||
                !Near(expected.floatValue, actual.floatValue) || expected.stringValue != actual.stringValue ||
                expected.mode != actual.mode || !Near(expected.vectorX, actual.vectorX) ||
                !Near(expected.vectorY, actual.vectorY) || !Near(expected.vectorZ, actual.vectorZ) ||
                !Near(expected.colorR, actual.colorR) || !Near(expected.colorG, actual.colorG) ||
                !Near(expected.colorB, actual.colorB) || !Near(expected.colorA, actual.colorA) ||
                !Near(expected.rootX, actual.rootX) || !Near(expected.rootY, actual.rootY) ||
                !Near(expected.rootZ, actual.rootZ) || expected.targetAId != actual.targetAId ||
                expected.targetBId != actual.targetBId ||
                expected.referenceTarget != actual.referenceTarget || expected.stateCount != actual.stateCount ||
                expected.firstState != actual.firstState || expected.firstStateId != actual.firstStateId ||
                expected.firstTransitionEvent != actual.firstTransitionEvent ||
                expected.firstTransitionTarget != actual.firstTransitionTarget ||
                expected.firstActionKind != actual.firstActionKind ||
                expected.firstActionLabel != actual.firstActionLabel ||
                !Near(expected.firstActionScalar, actual.firstActionScalar) ||
                expected.secondState != actual.secondState || expected.secondStateId != actual.secondStateId ||
                expected.secondTransitionEvent != actual.secondTransitionEvent ||
                expected.secondTransitionTarget != actual.secondTransitionTarget ||
                expected.nestedActionKind != actual.nestedActionKind ||
                expected.nestedActionLabel != actual.nestedActionLabel ||
                !Near(expected.nestedActionScalar, actual.nestedActionScalar))
            {
                throw new InvalidDataException("Unity save/reload changed serialized fields in " + context + ".");
            }
        }

        private static bool Near(float left, float right)
        {
            return Math.Abs(left - right) <= 0.0001f;
        }

        private static string CopyArtifact(string source, string destination)
        {
            if (!File.Exists(source))
            {
                throw new FileNotFoundException("Unity output is missing " + source, source);
            }
            File.Copy(source, destination, true);
            return destination;
        }

        private static string Relative(string root, string fullPath)
        {
            string prefix = Path.GetFullPath(root) + Path.DirectorySeparatorChar;
            string full = Path.GetFullPath(fullPath);
            if (!full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("Artifact escaped output directory.");
            }
            return full.Substring(prefix.Length).Replace(Path.DirectorySeparatorChar, '/');
        }

        private static string Sha256(string path)
        {
            using (SHA256 sha = SHA256.Create())
            using (FileStream stream = File.OpenRead(path))
            {
                byte[] hash = sha.ComputeHash(stream);
                StringBuilder result = new StringBuilder(hash.Length * 2);
                for (int index = 0; index < hash.Length; index++)
                {
                    result.Append(hash[index].ToString("x2"));
                }
                return result.ToString();
            }
        }
    }
}
