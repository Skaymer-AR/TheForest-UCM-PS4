// Synthetic stand-ins for compiling against a subset of UnityEngine.
// NOT a replacement for the Unity 5.6 or PS4 engine assemblies.
using System;

namespace UnityEngine
{
    public class Object
    {
        public static void DontDestroyOnLoad(Object obj) { }
    }

    public class GameObject : Object
    {
        public GameObject(string name) { }

        public T AddComponent<T>() where T : MonoBehaviour, new()
        {
            T component = new T();
            component.gameObject = this;
            return component;
        }
    }

    public class MonoBehaviour : Object
    {
        public GameObject gameObject;
        public static void Destroy(Object obj) { }
    }

    public enum RuntimeInitializeLoadType { AfterSceneLoad }

    [AttributeUsage(AttributeTargets.Method)]
    public class RuntimeInitializeOnLoadMethodAttribute : Attribute
    {
        public RuntimeInitializeOnLoadMethodAttribute(RuntimeInitializeLoadType when) { }
    }

    public struct Rect
    {
        public Rect(float x, float y, float width, float height) { }
    }

    public static class GUI
    {
        public static void Label(Rect rect, string text) { }
        public static void Box(Rect rect, string text) { }
    }

    public enum KeyCode
    {
        Q, E, UpArrow, DownArrow, LeftArrow, RightArrow, Return, Escape
    }

    public static class Input
    {
        public static bool GetKey(KeyCode key) { return false; }
    }
}
