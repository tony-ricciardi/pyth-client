#pragma once

#include <pc/ext/verify.hpp>
#include <pc/mem_map.hpp>

#include <memory>
#include <vector>

namespace pc
{
  template < typename T >
  class column
  {
  protected:
    column() = default;

  public:
    virtual ~column() = default;

    column( column const& ) = delete;
    column& operator=( column const& ) = delete;

    [[ nodiscard ]] virtual size_t size() const = 0;
    [[ nodiscard ]] virtual T const* begin() const = 0;
    [[ nodiscard ]] T const* end() { return begin() + size(); }
  };

  // Dynamically generated unit test input.
  template < typename T >
  struct vec_column
    : public column< T >
  {
    vec_column() = default;
    std::vector< T > impl_;

    [[ nodiscard ]] size_t size() const override { return impl_.size(); }
    [[ nodiscard ]] T const* begin() const override { return &*impl_.begin(); }
  };

  // Mem-mapped binary file generated by a python test.
  template < typename T >
  class file_column
    : public column< T >
  {
    pc::mem_map impl_;

  public:
    explicit file_column( std::string const& path )
    {
      impl_.set_file( path );
      impl_.init();
      PC_ASSERT_GT( impl_.size(), 0 );
      PC_ASSERT_EQ( impl_.size() % sizeof( T ), 0 );
    }

    [[ nodiscard ]]
    size_t size() const override
    {
      return impl_.size() / sizeof( T );
    }

    [[ nodiscard ]]
    T const* begin() const override
    {
      return reinterpret_cast< T const* >( impl_.data() );
    }
  };
}
