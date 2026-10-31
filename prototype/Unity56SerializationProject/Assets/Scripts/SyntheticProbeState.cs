using System;

namespace UcmUnitySerializationProbe
{
    [Serializable]
    public sealed class SyntheticProbeAction
    {
        public string kind;
        public string label;
        public float scalar;
    }

    [Serializable]
    public sealed class SyntheticProbeState
    {
        public string name;
        public int id;
        public string transitionEvent;
        public string transitionTarget;
        public SyntheticProbeAction action;
    }
}
