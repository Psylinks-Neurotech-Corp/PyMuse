cmake_minimum_required(VERSION 3.20)
project(muse_wrapper LANGUAGES CXX)

# Options
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)

# Configure Muse SDK root (can be overridden by -DMUSE_SDK_ROOT=...)
if(NOT DEFINED MUSE_SDK_ROOT)
  # Default to repo-local SDK path
  get_filename_component(REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
  set(MUSE_SDK_ROOT "${REPO_ROOT}/libmuse_windows_8.0.5/libmuse_windows_8.0.5")
endif()
# Always canonicalize to an absolute path to avoid VS relative-path issues
get_filename_component(MUSE_SDK_ROOT "${MUSE_SDK_ROOT}" ABSOLUTE)

message(STATUS "Muse SDK root: ${MUSE_SDK_ROOT}")

# pybind11 (header-only) via FetchContent
include(FetchContent)
FetchContent_Declare(
  pybind11
  GIT_REPOSITORY https://github.com/pybind/pybind11.git
  GIT_TAG v2.11.1
  GIT_SHALLOW TRUE
)
FetchContent_MakeAvailable(pybind11)

# Validate headers exist
if(NOT EXISTS "${MUSE_SDK_ROOT}/include/api/muse_manager_windows.h")
  message(FATAL_ERROR "Muse SDK headers not found at ${MUSE_SDK_ROOT}/include/api. Set MUSE_SDK_ROOT to the folder that contains 'include/api/...'.")
endif()

# Include dirs (global for safety; also set per-target below)
include_directories(
  "${MUSE_SDK_ROOT}/include"
  "${MUSE_SDK_ROOT}/include/api"
)

# Library selection (x64 release by default)
set(MUSE_LIB_DIR "${MUSE_SDK_ROOT}/lib/release/x64")
set(MUSE_DLL "${MUSE_LIB_DIR}/libmuse.dll")

# Use find_library so MSVC doesn't append .lib twice
find_library(MUSE_LIB
  NAMES libmuse-wrt libmuse-uwp
  PATHS ${MUSE_LIB_DIR}
  NO_DEFAULT_PATH
)

if(NOT MUSE_LIB)
  message(FATAL_ERROR "Muse library not found in ${MUSE_LIB_DIR}. Set MUSE_SDK_ROOT to the libmuse path.")
endif()

pybind11_add_module(muse_wrapper MODULE
  src/muse_wrapper.cpp
)

target_include_directories(muse_wrapper PRIVATE "${MUSE_SDK_ROOT}/include" "${MUSE_SDK_ROOT}/include/api")
target_link_libraries(muse_wrapper PRIVATE ${MUSE_LIB})

# Copy DLL next to the extension so Python can load it
add_custom_command(TARGET muse_wrapper POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E echo "Copying libmuse.dll from: ${MUSE_DLL}"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
          "${MUSE_DLL}"
          "$<TARGET_FILE_DIR:muse_wrapper>"
)

# Nice output directory
set_target_properties(muse_wrapper PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/python
  RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/python
  OUTPUT_NAME "muse_wrapper"
)

# Also copy artifacts into a stable 'bin' folder inside the source tree for easy bundling
set(WRAPPER_BIN_DIR "${CMAKE_CURRENT_LIST_DIR}/bin")
file(MAKE_DIRECTORY "${WRAPPER_BIN_DIR}")

add_custom_command(TARGET muse_wrapper POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
          "$<TARGET_FILE:muse_wrapper>"
          "${WRAPPER_BIN_DIR}/"
)
add_custom_command(TARGET muse_wrapper POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
          "${MUSE_DLL}"
          "${WRAPPER_BIN_DIR}/"
)
