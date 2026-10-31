using AssetsTools.NET;
using AssetsTools.NET.Extra;

internal static class Program
{
    private const string UnityVersion = "5.6.6f2";
    private const string SceneFile = "synthetic_scene.assets";
    private const string LibraryFile = "synthetic_library.assets";
    private const string OriginalName = "Synthetic Menu Host";
    private const string RewrittenName = "Synthetic Menu Host (AssetsTools.NET rewrite)";
    private const long GameObjectId = 100;
    private const long TransformId = 200;
    private const long MonoBehaviourId = 300;
    private const long MonoScriptId = 900;

    private sealed record Graph(string GameObjectName, int ComponentCount,
        int SceneObjectCount, int LibraryObjectCount, string MonoScriptClass,
        string MonoScriptNamespace, string MonoScriptAssembly);

    private static int Main(string[] args)
    {
        string stage = "argument validation";
        try
        {
            if (args.Length > 0 && args[0] == "editor-bundle")
            {
                return UnityEditorBundleProbe.Run(args.Skip(1).ToArray());
            }
            if (args.Length != 3)
            {
                throw new ArgumentException(
                    "usage: UnityFormat17Validator <classdata.tpk> <fixture-dir> <roundtrip-dir>");
            }

            string classDataPath = Path.GetFullPath(args[0]);
            string fixtureDir = Path.GetFullPath(args[1]);
            string roundtripDir = Path.GetFullPath(args[2]);
            Directory.CreateDirectory(roundtripDir);

            stage = "initial AssetsTools.NET read";
            Graph before = ReadAndValidate(classDataPath, fixtureDir, OriginalName);
            string playmakerBefore = PlayMakerFormat17Probe.Validate(classDataPath, fixtureDir,
                PlayMakerFormat17Probe.OriginalName);
            stage = "AssetsTools.NET rewrite";
            RewriteWithAssetsTools(classDataPath, fixtureDir, roundtripDir);
            PlayMakerFormat17Probe.Rewrite(classDataPath, fixtureDir, roundtripDir);
            stage = "AssetsTools.NET reread";
            Graph after = ReadAndValidate(classDataPath, roundtripDir, RewrittenName);
            string playmakerAfter = PlayMakerFormat17Probe.Validate(classDataPath,
                roundtripDir, PlayMakerFormat17Probe.RewrittenName);
            if (playmakerBefore != playmakerAfter)
                throw new InvalidDataException("AssetsTools.NET changed opaque PlayMakerFSM component bytes");
            if ((before with { GameObjectName = RewrittenName }) != after)
                throw new InvalidDataException("AssetsTools.NET rewrite changed graph semantics");

            Console.WriteLine("AssetsTools.NET 3.0.5: PASS");
            Console.WriteLine($"Unity serialized format: 17 ({UnityVersion})");
            Console.WriteLine("Type database: classdata.tpk loaded; embedded TypeTrees not used");
            Console.WriteLine("Validated: GameObject, Transform, MonoBehaviour base, MonoScript PPtr and external dependency");
            Console.WriteLine("Write/re-read: PASS (GameObject name changed through SetNewData)");
            Console.WriteLine($"Scene objects: {after.SceneObjectCount}; library objects: {after.LibraryObjectCount}");
            Console.WriteLine("PlayMakerFSM container: PASS (synthetic MonoBehaviour, raw payload SHA-256 retained)");
            Console.WriteLine("PlayMaker private schema: NOT validated by AssetsTools.NET class database");
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"AssetsTools.NET format-17 validation failed during {stage}:");
            Console.Error.WriteLine(ex);
            return 1;
        }
    }

    private static Graph ReadAndValidate(string classDataPath, string root, string expectedName)
    {
        var manager = new AssetsManager();
        manager.LoadClassPackage(classDataPath);
        manager.LoadClassDatabaseFromPackage(UnityVersion);
        Console.WriteLine($"Loaded class database for {UnityVersion}");

        AssetsFileInstance library = manager.LoadAssetsFile(Path.Combine(root, LibraryFile));
        AssetsFileInstance scene = manager.LoadAssetsFile(Path.Combine(root, SceneFile));
        Console.WriteLine("Loaded both serialized files");
        ValidateHeader(library.file, LibraryFile);
        ValidateHeader(scene.file, SceneFile);
        if (scene.file.Metadata.TypeTreeEnabled || library.file.Metadata.TypeTreeEnabled)
            throw new InvalidDataException("fixture unexpectedly embeds a TypeTree");

        AssetFileInfo goInfo = Find(scene.file, 1, GameObjectId);
        AssetFileInfo transformInfo = Find(scene.file, 4, TransformId);
        AssetFileInfo monoInfo = Find(scene.file, 114, MonoBehaviourId);
        AssetFileInfo scriptInfo = Find(library.file, 115, MonoScriptId);
        EnsureUniquePathIds(scene.file, SceneFile);
        EnsureUniquePathIds(library.file, LibraryFile);

        Console.WriteLine("Deserializing GameObject");
        AssetTypeValueField go = manager.GetBaseField(scene, goInfo);
        string gameObjectName = Field(go, "m_Name").AsString;
        if (gameObjectName != expectedName)
            throw new InvalidDataException($"GameObject name mismatch: {gameObjectName}");
        if (Field(go, "m_IsActive").AsBool != true)
            throw new InvalidDataException("GameObject is not active");

        AssetTypeValueField components = Field(go, "m_Component.Array");
        if (components.Children.Count != 2)
            throw new InvalidDataException("GameObject must contain exactly two components");
        var componentIds = components.Children
            .Select(item => (FileId: Field(item, "component.m_FileID").AsInt,
                PathId: Field(item, "component.m_PathID").AsLong))
            .ToArray();
        if (!componentIds.SequenceEqual(new[] { (0, TransformId), (0, MonoBehaviourId) }))
            throw new InvalidDataException("GameObject component PPtrs are not the expected local objects");

        Console.WriteLine("Deserializing Transform");
        AssetTypeValueField transform = manager.GetBaseField(scene, transformInfo);
        AssertPPtr(transform, "m_GameObject", 0, GameObjectId, "Transform GameObject");
        AssertPPtr(transform, "m_Father", 0, 0, "root Transform father");
        if (Field(transform, "m_Children.Array").Children.Count != 0)
            throw new InvalidDataException("root Transform unexpectedly has children");
        AssertNear(Field(transform, "m_LocalPosition.x").AsFloat, 1.25f, "position.x");
        AssertNear(Field(transform, "m_LocalPosition.y").AsFloat, -2.5f, "position.y");
        AssertNear(Field(transform, "m_LocalPosition.z").AsFloat, 3.75f, "position.z");
        AssertNear(Field(transform, "m_LocalScale.x").AsFloat, 1.0f, "scale.x");

        Console.WriteLine("Deserializing MonoBehaviour base fields");
        AssetTypeValueField mono = manager.GetBaseField(scene, monoInfo);
        AssertPPtr(mono, "m_GameObject", 0, GameObjectId, "MonoBehaviour GameObject");
        if (Field(mono, "m_Enabled").AsBool != true)
            throw new InvalidDataException("MonoBehaviour base enabled flag is false");
        AssertPPtr(mono, "m_Script", 1, MonoScriptId, "MonoBehaviour MonoScript");
        if (scene.file.Metadata.ScriptTypes.Count != 1 ||
            scene.file.Metadata.ScriptTypes[0].FileId != 1 ||
            scene.file.Metadata.ScriptTypes[0].PathId != MonoScriptId)
            throw new InvalidDataException("format-17 script type table is inconsistent");
        if (scene.file.Metadata.Externals.Count != 1 ||
            Path.GetFileName(scene.file.Metadata.Externals[0].PathName) != LibraryFile)
            throw new InvalidDataException("external-file dependency table is inconsistent");
        if (monoInfo.GetScriptIndex(scene.file) != 0)
            throw new InvalidDataException("MonoBehaviour script type index is not zero");

        AssetsFileInstance dependency = scene.GetDependency(manager, 0)
            ?? throw new InvalidDataException("AssetsTools.NET could not resolve the external dependency");
        if (!ReferenceEquals(dependency.file, library.file))
            throw new InvalidDataException("external dependency resolved to the wrong file");
        Console.WriteLine("Deserializing external MonoScript");
        AssetTypeValueField script = manager.GetBaseField(dependency, scriptInfo);
        string scriptClass = Field(script, "m_ClassName").AsString;
        string scriptNamespace = Field(script, "m_Namespace").AsString;
        string scriptAssembly = Field(script, "m_AssemblyName").AsString;
        if (scriptClass != "SyntheticHost" || scriptNamespace != "FixtureOnly" ||
            scriptAssembly != "FixtureOnly.dll")
            throw new InvalidDataException("external MonoScript schema fields mismatch");
        if (Field(script, "m_IsEditorScript").AsBool)
            throw new InvalidDataException("fixture MonoScript editor flag is unexpectedly set");

        var graph = new Graph(gameObjectName, components.Children.Count,
            scene.file.Metadata.AssetInfos.Count, library.file.Metadata.AssetInfos.Count,
            scriptClass, scriptNamespace, scriptAssembly);
        manager.UnloadAll();
        return graph;
    }

    private static void RewriteWithAssetsTools(string classDataPath, string inputRoot,
        string outputRoot)
    {
        var manager = new AssetsManager();
        manager.LoadClassPackage(classDataPath);
        manager.LoadClassDatabaseFromPackage(UnityVersion);
        AssetsFileInstance library = manager.LoadAssetsFile(Path.Combine(inputRoot, LibraryFile));
        AssetsFileInstance scene = manager.LoadAssetsFile(Path.Combine(inputRoot, SceneFile));
        AssetFileInfo goInfo = Find(scene.file, 1, GameObjectId);
        AssetTypeValueField go = manager.GetBaseField(scene, goInfo);
        Field(go, "m_Name").AsString = RewrittenName;
        goInfo.SetNewData(go);

        using (var writer = new AssetsFileWriter(Path.Combine(outputRoot, LibraryFile)))
            library.file.Write(writer);
        using (var writer = new AssetsFileWriter(Path.Combine(outputRoot, SceneFile)))
            scene.file.Write(writer);
        manager.UnloadAll();
    }

    private static void ValidateHeader(AssetsFile file, string label)
    {
        if (file.Header.Version != 17 || file.Metadata.UnityVersion != UnityVersion)
            throw new InvalidDataException($"{label} is not Unity {UnityVersion}, serialized format 17");
        long fileLength = file.Reader.BaseStream.Length;
        long headerLength = file.Header.GetSize();
        if (file.Header.FileSize != fileLength ||
            file.Header.MetadataSize < 0 ||
            file.Header.DataOffset < headerLength + file.Header.MetadataSize ||
            file.Header.DataOffset > fileLength)
            throw new InvalidDataException($"{label} has inconsistent file, metadata, or data offsets");

        foreach (AssetFileInfo info in file.Metadata.AssetInfos)
        {
            long absoluteOffset = info.GetAbsoluteByteOffset(file);
            if (info.ByteOffset < 0 || info.ByteSize == 0 ||
                absoluteOffset < file.Header.DataOffset ||
                absoluteOffset > fileLength - info.ByteSize)
                throw new InvalidDataException($"{label} has an object descriptor outside the file");
            if (info.TypeIdOrIndex < 0 ||
                info.TypeIdOrIndex >= file.Metadata.TypeTreeTypes.Count)
                throw new InvalidDataException($"{label} has an invalid object type index");
        }
    }

    private static AssetFileInfo Find(AssetsFile file, int classId, long pathId)
    {
        AssetFileInfo? info = file.Metadata.AssetInfos.SingleOrDefault(item =>
            item.TypeId == classId && item.PathId == pathId);
        return info ?? throw new InvalidDataException(
            $"missing class {classId} PathID {pathId}");
    }

    private static void EnsureUniquePathIds(AssetsFile file, string label)
    {
        int distinct = file.Metadata.AssetInfos.Select(info => info.PathId).Distinct().Count();
        if (distinct != file.Metadata.AssetInfos.Count)
            throw new InvalidDataException($"{label} contains duplicate PathIDs");
    }

    private static AssetTypeValueField Field(AssetTypeValueField parent, string path)
    {
        AssetTypeValueField field = parent[path];
        return field.IsDummy
            ? throw new InvalidDataException($"AssetsTools.NET did not decode required field {path}")
            : field;
    }

    private static void AssertPPtr(AssetTypeValueField parent, string fieldName,
        int fileId, long pathId, string label)
    {
        if (Field(parent, $"{fieldName}.m_FileID").AsInt != fileId ||
            Field(parent, $"{fieldName}.m_PathID").AsLong != pathId)
            throw new InvalidDataException($"{label} PPtr is inconsistent");
    }

    private static void AssertNear(float actual, float expected, string label)
    {
        if (MathF.Abs(actual - expected) > 0.0001f)
            throw new InvalidDataException($"{label} mismatch: {actual} != {expected}");
    }

}
