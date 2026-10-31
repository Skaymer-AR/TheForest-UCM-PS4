using UnityEngine;

namespace UcmUnitySerializationProbe
{
    public enum SyntheticProbeMode
    {
        Closed = 0,
        Open = 1,
        Settings = 2
    }

    public sealed class SyntheticMenuHost : MonoBehaviour
    {
        public int intValue;
        public bool boolValue;
        public float floatValue;
        public string stringValue;
        public SyntheticProbeMode mode;
        public Vector3 vectorValue;
        public Color colorValue;
        public SyntheticProbeTarget referenceTarget;
        public SyntheticProbeState[] states;
    }
}
