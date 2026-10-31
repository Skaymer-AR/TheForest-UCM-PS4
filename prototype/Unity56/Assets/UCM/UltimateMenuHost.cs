using UnityEngine;

namespace TheForest.UCM
{
    // Standalone Unity 5.6 prototype. NOT part of the PS4 title or its metadata.
    // The bootstrap runs only when this script is compiled into a compatible Unity build.
    public sealed class UltimateMenuHost : MonoBehaviour
    {
        private static UltimateMenuHost _instance;
        private UcmMenuModel _menu;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Bootstrap()
        {
            if (_instance != null) return;
            GameObject host = new GameObject("TheForest.UCM.PrototypeHost");
            host.AddComponent<UltimateMenuHost>();
            Object.DontDestroyOnLoad(host);
        }

        private void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Destroy(gameObject);
                return;
            }
            _instance = this;
            _menu = new UcmMenuModel();
#if UNITY_EDITOR
            // Editor-only demo; does NOT map PS4 DualShock 4 or Rewired actions.
            if (UcmInputRegistry.Source == null)
                UcmInputRegistry.Source = new UcmEditorKeyboardInput();
#endif
        }

        private void Update()
        {
            if (_menu == null) return;
            IUcmInputSource source = UcmInputRegistry.Source;
            bool connected = false;
            UcmButton buttons = UcmButton.None;
            if (source == null || !source.TryRead(out connected, out buttons))
            {
                _menu.Tick(false, UcmButton.None);
                return;
            }
            _menu.Tick(connected, buttons);
        }

        private void OnGUI()
        {
            if (_menu == null || !_menu.Visible) return;

            GUI.Box(new Rect(48, 48, 650, 630), "");
            GUI.Label(new Rect(80, 102, 590, 32), "THE FOREST - ULTIMATE CHEATMENU");
            GUI.Label(new Rect(80, 146, 590, 26), "Offline AOT prototype - gameplay commands locked");
            GUI.Label(new Rect(80, 197, 590, 30), _menu.Category.ToString());

            int row = 0;
            foreach (UcmItem item in _menu.VisibleItems())
            {
                string label = item.Label;
                if (!item.Available) label += "  [UNVERIFIED]";
                else if (item.Kind == UcmItemKind.Toggle)
                    label += item.Value != 0 ? "  ON" : "  OFF";
                else if (item.Kind == UcmItemKind.Slider)
                    label += "  " + item.Value.ToString() + "%";

                if (row == _menu.SelectedIndex)
                    GUI.Box(new Rect(64, 232 + row * 48, 618, 42), "");
                GUI.Label(new Rect(82, 240 + row * 48, 592, 32), label);
                row++;
            }
            if (row == 0)
                GUI.Label(new Rect(82, 240, 592, 32), "No entries in this category");

            GUI.Label(new Rect(80, 578, 590, 28), "L1+R1: menu | D-pad: navigation");
            GUI.Label(new Rect(80, 612, 590, 28), "L1/R1: category | Cross: select | Circle: close");
        }

        private void OnDestroy()
        {
            if (_instance == this) _instance = null;
        }
    }

#if UNITY_EDITOR
    // For checking this prototype inside a separate Unity Editor project only.
    internal sealed class UcmEditorKeyboardInput : IUcmInputSource
    {
        public bool TryRead(out bool connected, out UcmButton buttons)
        {
            connected = true;
            buttons = UcmButton.None;
            if (Input.GetKey(KeyCode.Q)) buttons |= UcmButton.L1;
            if (Input.GetKey(KeyCode.E)) buttons |= UcmButton.R1;
            if (Input.GetKey(KeyCode.UpArrow)) buttons |= UcmButton.Up;
            if (Input.GetKey(KeyCode.DownArrow)) buttons |= UcmButton.Down;
            if (Input.GetKey(KeyCode.LeftArrow)) buttons |= UcmButton.Left;
            if (Input.GetKey(KeyCode.RightArrow)) buttons |= UcmButton.Right;
            if (Input.GetKey(KeyCode.Return)) buttons |= UcmButton.Cross;
            if (Input.GetKey(KeyCode.Escape)) buttons |= UcmButton.Circle;
            return true;
        }
    }
#endif
}
