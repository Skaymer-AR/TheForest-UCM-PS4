// Compile-only symbols for the Unity 5.6 Editor probe. These stubs never
// create serialized output and are not evidence that Unity ran the probe.
using System;

namespace UnityEngine
{
    public class Object
    {
        public string name { get; set; }
    }

    public class Component : Object
    {
        public GameObject gameObject;
        public Transform transform { get { return gameObject.transform; } }
    }

    public class MonoBehaviour : Component
    {
    }

    public class Transform : Component
    {
        public Vector3 position;
        public void SetParent(Transform parent, bool worldPositionStays) { }
        public Transform Find(string name) { return null; }
    }

    public struct Vector3
    {
        public float x;
        public float y;
        public float z;

        public Vector3(float xValue, float yValue, float zValue)
        {
            x = xValue;
            y = yValue;
            z = zValue;
        }
    }

    public struct Color
    {
        public float r;
        public float g;
        public float b;
        public float a;

        public Color(float red, float green, float blue, float alpha)
        {
            r = red;
            g = green;
            b = blue;
            a = alpha;
        }
    }

    public class GameObject : Object
    {
        public Transform transform;

        public GameObject(string objectName)
        {
            name = objectName;
            transform = new Transform();
            transform.gameObject = this;
        }

        public T AddComponent<T>() where T : Component, new()
        {
            T component = new T();
            component.gameObject = this;
            return component;
        }

        public T GetComponent<T>() where T : Component
        {
            return null;
        }

        public static GameObject Find(string objectName)
        {
            return null;
        }
    }

    public static class Application
    {
        public static string unityVersion = "stub";
        public static string dataPath = "Assets";
    }

    public static class Debug
    {
        public static void Log(object value) { }
        public static void LogException(Exception exception) { }
    }

    public static class JsonUtility
    {
        public static string ToJson(object value, bool prettyPrint) { return "{}"; }
    }
}

namespace UnityEngine.SceneManagement
{
    using UnityEngine;

    public struct Scene
    {
        public GameObject[] GetRootGameObjects() { return new GameObject[0]; }
    }

}

namespace UnityEditor
{
    using UnityEngine;

    public enum SerializationMode
    {
        Mixed,
        ForceText,
        ForceBinary
    }

    public static class EditorSettings
    {
        public static SerializationMode serializationMode;
    }

    public static class AssetDatabase
    {
        public static bool IsValidFolder(string path) { return false; }
        public static bool DeleteAsset(string path) { return true; }
        public static string CreateFolder(string parent, string name) { return name; }
        public static void SaveAssets() { }
        public static void Refresh() { }
        public static void ImportAsset(string path) { }
        public static T LoadAssetAtPath<T>(string path) where T : UnityEngine.Object { return null; }
    }

    public static class PrefabUtility
    {
        public static UnityEngine.Object CreatePrefab(string path, GameObject root) { return root; }
    }

    public enum BuildTarget
    {
        StandaloneLinux
    }

    [Flags]
    public enum BuildAssetBundleOptions
    {
        None = 0,
        UncompressedAssetBundle = 1,
        DisableWriteTypeTree = 2
    }

    public struct AssetBundleBuild
    {
        public string assetBundleName;
        public string[] assetNames;
    }

    public class AssetBundleManifest : Object
    {
    }

    public static class EditorUserBuildSettings
    {
        public static BuildTarget activeBuildTarget;
    }

    public static class BuildPipeline
    {
        public static AssetBundleManifest BuildAssetBundles(string outputPath,
            AssetBundleBuild[] builds, BuildAssetBundleOptions options, BuildTarget target)
        {
            return null;
        }
    }

    public static class EditorApplication
    {
        public static void Exit(int returnCode) { }
    }
}

namespace UnityEditor.SceneManagement
{
    using UnityEngine.SceneManagement;

    public enum NewSceneSetup
    {
        EmptyScene
    }

    public enum NewSceneMode
    {
        Single
    }

    public enum OpenSceneMode
    {
        Single
    }

    public static class EditorSceneManager
    {
        public static Scene NewScene(NewSceneSetup setup, NewSceneMode mode) { return new Scene(); }
        public static bool SaveScene(Scene scene, string path) { return true; }
        public static Scene OpenScene(string path, OpenSceneMode mode) { return new Scene(); }
    }
}
