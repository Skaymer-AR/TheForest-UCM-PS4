using System.Security.Cryptography;
using System.Text.Json;
using AssetsTools.NET;
using AssetsTools.NET.Extra;

// Reads AssetBundles produced by the synthetic Unity 5.6 Editor project.
// It never accepts a retail game asset as input through the documented runner.
internal static class UnityEditorBundleProbe
{
    private const string ExpectedUnityVersion = "5.6.6f2";

    private sealed class ObjectRow
    {
        public long pathId;
        public int classId;
        public string sha256 = "";
    }

    private sealed class LinkRow
    {
        public int fileId;
        public long pathId;
    }

    private sealed class GameObjectRow
    {
        public long pathId;
        public string name = "";
        public bool active;
        public List<LinkRow> components = new();
    }

    private sealed class TransformRow
    {
        public long pathId;
        public int gameObjectFileId;
        public long gameObjectPathId;
        public List<long> childPathIds = new();
        public int fatherFileId;
        public long fatherPathId;
    }

    private sealed class MonoBehaviourRow
    {
        public long pathId;
        public bool enabled;
        public int gameObjectFileId;
        public long gameObjectPathId;
        public int scriptFileId;
        public long scriptPathId;
    }

    private sealed class BundleReport
    {
        public uint formatVersion;
        public string unityVersion = "";
        public bool typeTreeEnabled;
        public string bundleSha256 = "";
        public string assetFileName = "";
        public long assetFileBytes;
        public List<ObjectRow> objects = new();
        public List<GameObjectRow> gameObjects = new();
        public List<TransformRow> transforms = new();
        public List<MonoBehaviourRow> monoBehaviours = new();
    }

    public static int Run(string[] args)
    {
        string stage = "argument validation";
        try
        {
            if (args.Length != 4)
            {
                throw new ArgumentException(
                    "usage: UnityFormat17Validator editor-bundle <classdata.tpk> <bundle> <extracted.assets> <report.json>");
            }

            string classDataPath = Path.GetFullPath(args[0]);
            string bundlePath = Path.GetFullPath(args[1]);
            string extractedPath = Path.GetFullPath(args[2]);
            string reportPath = Path.GetFullPath(args[3]);
            Directory.CreateDirectory(Path.GetDirectoryName(extractedPath)!);
            Directory.CreateDirectory(Path.GetDirectoryName(reportPath)!);

            stage = "AssetsTools.NET AssetBundle read";
            var manager = new AssetsManager();
            manager.LoadClassPackage(classDataPath);
            manager.LoadClassDatabaseFromPackage(ExpectedUnityVersion);
            BundleFileInstance bundle = manager.LoadBundleFile(bundlePath, true);

            AssetsFileInstance? assets = null;
            string assetName = "";
            string[] names = bundle.file.GetAllFileNames().ToArray();
            for (int index = 0; index < names.Length; index++)
            {
                if (!bundle.file.IsAssetsFile(index))
                    continue;
                AssetsFileInstance candidate = manager.LoadAssetsFileFromBundle(bundle, index, false);
                if (candidate.file.Metadata.AssetInfos.Any(item => item.TypeId == 1) &&
                    candidate.file.Metadata.AssetInfos.Any(item => item.TypeId == 4) &&
                    candidate.file.Metadata.AssetInfos.Any(item => item.TypeId == 114))
                {
                    assets = candidate;
                    assetName = names[index];
                    break;
                }
            }
            if (assets == null)
                throw new InvalidDataException("AssetBundle contains no Unity file with GameObject, Transform and MonoBehaviour objects.");

            stage = "format-17 type-tree-free asset validation";
            if (assets.file.Header.Version != 17 ||
                assets.file.Metadata.UnityVersion != ExpectedUnityVersion ||
                assets.file.Metadata.TypeTreeEnabled)
            {
                throw new InvalidDataException("AssetBundle payload is not Unity 5.6.6f2 format 17 without embedded TypeTrees.");
            }

            byte[] assetBytes = ReadSerializedFile(assets.file);
            if (assets.file.Header.FileSize != assetBytes.LongLength || assetBytes.Length < 64)
                throw new InvalidDataException("Extracted serialized-file length disagrees with its header.");
            File.WriteAllBytes(extractedPath, assetBytes);

            var summary = new BundleReport();
            summary.formatVersion = assets.file.Header.Version;
            summary.unityVersion = assets.file.Metadata.UnityVersion;
            summary.typeTreeEnabled = assets.file.Metadata.TypeTreeEnabled;
            long bundleLength = new FileInfo(bundlePath).Length;
            if (bundleLength <= 0 || bundleLength > 128L * 1024 * 1024)
                throw new InvalidDataException("Synthetic AssetBundle exceeds the 128 MiB validation limit.");
            summary.bundleSha256 = Sha256(File.ReadAllBytes(bundlePath));
            summary.assetFileName = Path.GetFileName(assetName);
            summary.assetFileBytes = assetBytes.LongLength;

            stage = "AssetsTools.NET object and PPtr decode";
            foreach (AssetFileInfo info in assets.file.Metadata.AssetInfos)
            {
                long offset = info.GetAbsoluteByteOffset(assets.file);
                long size = info.ByteSize;
                if (offset < 0 || size <= 0 || offset > assetBytes.LongLength - size)
                    throw new InvalidDataException("AssetBundle object descriptor is outside its serialized file.");
                byte[] objectBytes = new byte[checked((int)size)];
                Buffer.BlockCopy(assetBytes, checked((int)offset), objectBytes, 0, objectBytes.Length);
                summary.objects.Add(new ObjectRow
                {
                    pathId = info.PathId,
                    classId = info.TypeId,
                    sha256 = Sha256(objectBytes)
                });
            }
            summary.objects.Sort((left, right) => left.pathId.CompareTo(right.pathId));
            if (summary.objects.Select(row => row.pathId).Distinct().Count() != summary.objects.Count)
                throw new InvalidDataException("AssetBundle serialized file has duplicate PathIDs.");

            foreach (AssetFileInfo info in assets.file.Metadata.AssetInfos.Where(item => item.TypeId == 1))
            {
                AssetTypeValueField field = manager.GetBaseField(assets, info);
                AssetTypeValueField componentArray = Required(field, "m_Component.Array");
                var row = new GameObjectRow
                {
                    pathId = info.PathId,
                    name = Required(field, "m_Name").AsString,
                    active = Required(field, "m_IsActive").AsBool
                };
                foreach (AssetTypeValueField element in componentArray.Children)
                {
                    AssetTypeValueField pointer = Required(element, "component");
                    row.components.Add(ReadLink(pointer));
                }
                summary.gameObjects.Add(row);
            }
            summary.gameObjects.Sort((left, right) => left.pathId.CompareTo(right.pathId));
            if (!summary.gameObjects.Any(row => row.name == "UCM_SERIALIZATION_PROBE_ROOT"))
                throw new InvalidDataException("Unity AssetBundle is missing the synthetic probe root.");

            foreach (AssetFileInfo info in assets.file.Metadata.AssetInfos.Where(item => item.TypeId == 4))
            {
                AssetTypeValueField field = manager.GetBaseField(assets, info);
                AssetTypeValueField gameObject = Required(field, "m_GameObject");
                AssetTypeValueField father = Required(field, "m_Father");
                var row = new TransformRow
                {
                    pathId = info.PathId,
                    gameObjectFileId = Required(gameObject, "m_FileID").AsInt,
                    gameObjectPathId = Required(gameObject, "m_PathID").AsLong,
                    fatherFileId = Required(father, "m_FileID").AsInt,
                    fatherPathId = Required(father, "m_PathID").AsLong
                };
                foreach (AssetTypeValueField child in Required(field, "m_Children.Array").Children)
                    row.childPathIds.Add(Required(child, "m_PathID").AsLong);
                summary.transforms.Add(row);
            }
            summary.transforms.Sort((left, right) => left.pathId.CompareTo(right.pathId));

            foreach (AssetFileInfo info in assets.file.Metadata.AssetInfos.Where(item => item.TypeId == 114))
            {
                AssetTypeValueField field = manager.GetBaseField(assets, info);
                AssetTypeValueField gameObject = Required(field, "m_GameObject");
                AssetTypeValueField script = Required(field, "m_Script");
                summary.monoBehaviours.Add(new MonoBehaviourRow
                {
                    pathId = info.PathId,
                    enabled = Required(field, "m_Enabled").AsBool,
                    gameObjectFileId = Required(gameObject, "m_FileID").AsInt,
                    gameObjectPathId = Required(gameObject, "m_PathID").AsLong,
                    scriptFileId = Required(script, "m_FileID").AsInt,
                    scriptPathId = Required(script, "m_PathID").AsLong
                });
            }
            summary.monoBehaviours.Sort((left, right) => left.pathId.CompareTo(right.pathId));
            if (!summary.monoBehaviours.Any(row => row.enabled))
                throw new InvalidDataException("AssetBundle has no enabled MonoBehaviour.");

            var options = new JsonSerializerOptions { IncludeFields = true, WriteIndented = true };
            File.WriteAllText(reportPath, JsonSerializer.Serialize(summary, options));
            manager.UnloadAll();
            Console.WriteLine("AssetsTools.NET AssetBundle payload: PASS");
            Console.WriteLine("Unity format/version: 17 / 5.6.6f2; type trees disabled for independent Python parsing");
            Console.WriteLine($"Objects: {summary.objects.Count}; GameObjects: {summary.gameObjects.Count}; " +
                $"Transforms: {summary.transforms.Count}; MonoBehaviours: {summary.monoBehaviours.Count}");
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"AssetsTools.NET Editor bundle validation failed during {stage}:");
            Console.Error.WriteLine(ex);
            return 1;
        }
    }

    private static byte[] ReadSerializedFile(AssetsFile file)
    {
        Stream stream = file.Reader.BaseStream;
        long length = file.Header.FileSize;
        if (!stream.CanSeek || length <= 0 || length > 128L * 1024 * 1024 || length > stream.Length)
            throw new InvalidDataException("Serialized-file stream length is outside the probe limit.");
        stream.Position = 0;
        byte[] bytes = new byte[checked((int)length)];
        int total = 0;
        while (total < bytes.Length)
        {
            int count = stream.Read(bytes, total, bytes.Length - total);
            if (count == 0)
                throw new EndOfStreamException("Short read while extracting the Editor AssetBundle payload.");
            total += count;
        }
        return bytes;
    }

    private static AssetTypeValueField Required(AssetTypeValueField parent, string path)
    {
        AssetTypeValueField field = parent[path];
        if (field.IsDummy)
            throw new InvalidDataException("AssetsTools.NET class database could not decode " + path);
        return field;
    }

    private static LinkRow ReadLink(AssetTypeValueField pointer)
    {
        return new LinkRow
        {
            fileId = Required(pointer, "m_FileID").AsInt,
            pathId = Required(pointer, "m_PathID").AsLong
        };
    }

    private static string Sha256(byte[] bytes)
    {
        return Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    }
}
