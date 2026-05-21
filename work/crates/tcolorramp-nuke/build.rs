use std::path::PathBuf;

fn main() {
    println!("cargo:rustc-check-cfg=cfg(tcolor_ramp_native)");
    println!("cargo:rerun-if-env-changed=NUKE_SOURCE_PATH");
    println!("cargo:rerun-if-env-changed=PLATFORM_NAME");
    println!("cargo:rerun-if-env-changed=CPP_VERSION");
    println!("cargo:rerun-if-changed=src/tcolor_ramp.cpp");

    let nuke_root = if let Ok(sources) = std::env::var("NUKE_SOURCE_PATH") {
        PathBuf::from(sources)
    } else {
        println!("cargo:warning=NUKE_SOURCE_PATH not set; skipping native TColorRamp build.");
        return;
    };
    let nuke_path = nuke_root.join("include");

    let platform_name = if let Ok(name) = std::env::var("PLATFORM_NAME") {
        name
    } else {
        println!("cargo:warning=PLATFORM_NAME not set; skipping native TColorRamp build.");
        return;
    };

    let cpp_version = std::env::var("CPP_VERSION").unwrap_or_else(|_| "17".to_string());

    let mut builder = cc::Build::new();
    builder
        .cpp(true)
        .std(&format!("c++{cpp_version}"))
        .file("src/tcolor_ramp.cpp")
        .include(&nuke_path)
        .flag_if_supported("-DGLEW_NO_GLU");

    if platform_name == "windows" {
        builder
            .define("_CPPUNWIND", "1")
            .define("NOMINMAX", "1")
            .define("_USE_MATH_DEFINES", "1")
            .flag("/EHsc");
    } else if platform_name == "linux" {
        builder
            .flag("-fPIC")
            .flag_if_supported("-Wno-deprecated-copy-with-user-provided-copy")
            .flag_if_supported("-Wno-ignored-qualifiers")
            .flag_if_supported("-Wno-date-time")
            .flag_if_supported("-Wno-unused-parameter");

        if std::env::var("USE_CXX11_ABI").is_ok() {
            builder.flag("-D_GLIBCXX_USE_CXX11_ABI=1");
        }
    } else if platform_name == "macos" {
        builder
            .flag_if_supported("-Wno-deprecated-copy-with-user-provided-copy")
            .flag_if_supported("-Wno-ignored-qualifiers")
            .flag_if_supported("-Wno-date-time")
            .flag_if_supported("-Wno-unused-parameter");
    }

    builder.compile("tcolorramp-nuke");
    println!("cargo:rustc-cfg=tcolor_ramp_native");

    println!("cargo:rustc-link-search=all={}", nuke_root.display());
    println!("cargo:rustc-link-lib=dylib=DDImage");
}
